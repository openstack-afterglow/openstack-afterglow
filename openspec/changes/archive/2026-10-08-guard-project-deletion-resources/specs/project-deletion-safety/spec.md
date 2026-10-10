## ADDED Requirements

### Requirement: Project deletion requires a fresh allocated-resource check

The administrator project list SHALL inspect actual target-project allocations before enabling deletion. The backend SHALL repeat that inspection immediately before every Keystone project DELETE, regardless of whether the caller used the UI preflight. Cached dashboards and quota limits SHALL NOT prove resource absence. Stopped or error-state resources SHALL count as allocated. Reads SHALL exhaust provider pagination and filter target-project ownership; shared resources owned by another project SHALL NOT count. The automatically created default security group alone SHALL NOT block an otherwise empty project.

#### Scenario: A stopped instance and detached volume remain
- **WHEN** deletion is inspected for a project containing a stopped instance or an available, detached volume
- **THEN** the report lists the remaining resource counts and the UI and backend refuse project deletion

#### Scenario: A later resource page cannot be read
- **WHEN** any required or catalog-present resource read fails, is denied or is incomplete
- **THEN** the report identifies an unavailable check, does not present that result as zero, and DELETE returns 503 without deleting the project

#### Scenario: A resource appears after preflight
- **WHEN** a project was empty during UI preflight but contains a resource during final DELETE inspection
- **THEN** DELETE returns 409 with the current blocking report and the modal stays open

#### Scenario: An optional resource service is not deployed
- **WHEN** the authenticated catalog confirms absence of an optional resource service
- **THEN** its check is disclosed as skipped and does not independently prevent deletion

#### Scenario: The request token lacks native admin context
- **WHEN** the Afterglow system administrator's project-scoped token lacks the native `admin` role or admin-project context
- **THEN** every resource kind is unavailable without provider reads, DELETE returns 503 without Keystone deletion, and the modal explains switching to an administrator project

#### Scenario: An administrator inspects a project other than the token project
- **WHEN** the catalog-present service supports native administrator inventory
- **THEN** its complete global/target-filtered listing is checked for exact target ownership without requiring an unnecessary tenant password rescope
- **AND** default-denied global endpoints such as Heat `global_tenant` are not required

#### Scenario: A catalog-present account-scoped service cannot verify the target
- **WHEN** Swift/RGW or Barbican is present but the caller token/account cannot verify the target project's inventory
- **THEN** its result is unavailable, DELETE returns 503 without Keystone deletion, and the modal explains administrator scope limitations and target-project authorization/recheck

#### Scenario: Trove administrator configuration inventory lacks owners
- **WHEN** the provider lists configurations without project ownership metadata
- **THEN** the check remains unavailable even if the administrator token is target-scoped, rather than assigning global rows to the target by assumption

#### Scenario: The selected project changes during inspection
- **WHEN** the modal closes or its target/auth scope changes while inspection is pending
- **THEN** the late response cannot authorize deletion or update the new target's report

#### Scenario: An empty project is explicitly confirmed
- **WHEN** all applicable resource checks succeed with no owned allocations and the user confirms deletion
- **THEN** the backend repeats the inspection and deletes only that project, without automatically deleting cloud resources
