## MODIFIED Requirements

### Requirement: Administrator database inventory represents tenant Trove resources

The administrator database inventory SHALL obtain all non-deleted tenant-created database instances from Trove's authenticated management API, SHALL expose each instance's owning project, and SHALL NOT embed control-plane MySQL monitoring on the resource page.

#### Scenario: System administrator lists tenant databases

- **WHEN** a system administrator requests `GET /api/v1/database-instances?all_projects=true`
- **THEN** the backend queries Trove `/mgmt/instances` through the database proxy
- **AND** returns every non-deleted instance with `tenant_id` normalized to `project_id`

#### Scenario: Trove management inventory is unavailable

- **WHEN** the Trove management request fails or returns a malformed instances collection
- **THEN** the API returns an error instead of an empty list
- **AND** the administrator page presents an explicit load failure rather than the no-instances state

#### Scenario: Administrator views database resources

- **WHEN** the administrator database page renders a successful inventory
- **THEN** it displays tenant-created Trove instances and their owning projects
- **AND** it does not render the generic `mysqld_exporter` dashboard used for OpenStack infrastructure monitoring
