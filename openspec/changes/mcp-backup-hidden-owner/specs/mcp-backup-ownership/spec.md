## ADDED Requirements

### Requirement: MCP backup ownership survives a hidden owner attribute
The MCP backup tools SHALL accept a backup whose owner `project_id` Cinder hides only when the connection was authenticated for exactly the requested project and the backup's parent volume is owned by that project. They SHALL reject a visible owner that differs, a connection without that proof, a proof for another project and a parent volume of another project.

#### Scenario: Reader lists backups
- **WHEN** a reader credential lists backups and Cinder omits `project_id`
- **THEN** the project's backups are returned with source volume, size and status only

#### Scenario: Member previews and requests a backup delete
- **WHEN** a member credential deletes an available backup whose owner is hidden
- **THEN** the adapter revalidates the backup and parent volume and sends a non-force delete

#### Scenario: No scope proof
- **WHEN** the connection has no authenticated-project proof or proves another project
- **THEN** the backup is rejected as unproven

#### Scenario: Foreign visible owner
- **WHEN** Cinder shows a different owner project
- **THEN** the backup is rejected even if the connection proves the requested project
