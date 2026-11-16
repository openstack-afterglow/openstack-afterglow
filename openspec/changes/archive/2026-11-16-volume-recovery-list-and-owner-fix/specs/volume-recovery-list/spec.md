## ADDED Requirements

### Requirement: Recovery lists show only volumes with recovery points
The volume backup and volume snapshot pages SHALL list a source volume only when it has at least one backup (snapshot). A volume without recovery points SHALL still open through its detail URL and SHALL appear in the list as soon as a recovery point is created.

#### Scenario: Volume without backups
- **WHEN** the project has a volume with no backup
- **THEN** the backup page does not list it, and creating a backup from the volume list makes it appear

#### Scenario: No volume has recovery points
- **WHEN** no volume has a backup and no search is active
- **THEN** the page shows an explanatory empty state

### Requirement: Automatic origin survives a hidden owner attribute
The system SHALL classify an automatic backup or snapshot using the project the session token is scoped to when Cinder omits the owner `project_id`, and SHALL NOT use the logical workspace, a visible foreign owner, a cross-project read or an unproven connection for that purpose.

#### Scenario: Member session hides project_id
- **WHEN** a member lists backups and Cinder returns no `project_id` for an automatic backup of the token's project
- **THEN** the backup is reported as automatic with its tier

#### Scenario: Cross-project or unproven read
- **WHEN** the read uses `all_projects` or the connection has no authenticated project
- **THEN** an owner that Cinder did not show stays unknown and the point is reported as manual

### Requirement: Volume list shows recovery capacity
The volume list summary SHALL show the number of backups and the sum of backup and snapshot sizes, SHALL label them as source-volume sizes rather than consumed space, and SHALL show an unknown marker instead of zero when the inventory cannot be read.

#### Scenario: Backup inventory unreadable
- **WHEN** the backup list request fails
- **THEN** the backup count and capacity show `—`

### Requirement: Refresh patches only changed rows
A table refresh SHALL NOT replace an already shown list with a loader, SHALL keep rows whose data is unchanged, and SHALL animate added, removed and changed rows only. A replacement of more than six rows at once SHALL NOT animate.

#### Scenario: One row changes
- **WHEN** a refresh returns the same rows with one changed value
- **THEN** every row node is retained and only the changed row flashes

#### Scenario: Page turn
- **WHEN** a page turn replaces every row of a ten-row table
- **THEN** no row animation runs and the outgoing rows are removed at once
