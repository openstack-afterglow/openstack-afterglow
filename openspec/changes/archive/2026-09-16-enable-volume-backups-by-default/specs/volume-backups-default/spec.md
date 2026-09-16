## MODIFIED Requirements

### Requirement: Volume backups are visible by default

Afterglow MUST initialize `volumeBackups` as enabled when no browser-local preference exists and MUST use the same declared default during server rendering.

#### Scenario: Fresh browser opens Afterglow

- **WHEN** the browser has no `afterglow.beta.volumeBackups` value
- **THEN** the volume-backup feature state is enabled
- **AND** volume-backup navigation is included

#### Scenario: Browser explicitly disables volume backups

- **WHEN** `afterglow.beta.volumeBackups` is stored as `false`
- **THEN** the volume-backup feature state remains disabled for that browser

### Requirement: Other beta defaults remain unchanged

Afterglow MUST NOT enable unrelated beta features as a side effect of the volume-backup default change.

#### Scenario: Fresh browser initializes beta features

- **WHEN** no beta-feature preferences exist
- **THEN** `volumeBackups` is enabled
- **AND** all other beta features retain their previously declared defaults

### Requirement: Deployment readiness is verified independently

The rollout MUST distinguish frontend feature visibility from Cinder backup-service readiness and MUST NOT infer service readiness from the navigation state alone.

#### Scenario: Production rollout completes

- **WHEN** the new frontend digest is running
- **THEN** every controller reports that digest or its matching immutable image ID
- **AND** Cinder backup-service status is checked separately
- **AND** disabled Swift and Zun flags remain false in the deployed site configuration
