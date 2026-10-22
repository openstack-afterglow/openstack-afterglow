## ADDED Requirements

### Requirement: Local Lumen must not outrun the schema of Kolla services sharing its database
While a Kolla-deployed Lumen reads the same database as the local stack, the local stack SHALL run the same Lumen source revision and SHALL NOT start a migration job from a newer tree. Local builds SHALL select that source through the canonical Dockerfile and a build-context setting, not an alternate image path. A missing selected source SHALL stop startup before any container starts.

#### Scenario: Pinned compatible source
- **WHEN** `LUMEN_BUILD_CONTEXT` names an extracted copy of the deployed revision
- **THEN** every Lumen image builds from that source and no non-Lumen service follows the selection

#### Scenario: Pinned source is unavailable
- **WHEN** the selected source has no Dockerfile
- **THEN** the runner fails with the unavailable-source message and starts nothing

### Requirement: The existing Lumen encryption key stays scoped to Lumen services
The key that decrypts stored provider credentials SHALL reach only the three Lumen services through a private owner-only file. An existing key SHALL be preserved and never rotated, a missing key SHALL be generated once, and the key SHALL NOT appear in the shared environment of other services or in logs.

#### Scenario: Existing key
- **WHEN** a scoped key file already exists
- **THEN** the three Lumen services receive that exact key and no other service does

#### Scenario: No key yet
- **WHEN** the file is absent
- **THEN** one owner-only key is generated and the next run leaves it unchanged

### Requirement: Provider authentication UI follows the native provider contract
The administrator provider screen SHALL show account management only when the authenticated provider response carries a valid `selection_policy`. Otherwise it SHALL use provider-level API key rotation and subscription authentication and SHALL NOT call account or credential routes. The presence of the field is a presentation capability and never an authorization grant.

#### Scenario: Old native provider
- **WHEN** a provider response has no or an unknown `selection_policy`
- **THEN** the screen offers provider-level key and subscription flows and makes no account route request

#### Scenario: Account-native provider
- **WHEN** the response carries `priority`, `weighted` or `explicit`
- **THEN** the account panel is shown and the legacy component is not
