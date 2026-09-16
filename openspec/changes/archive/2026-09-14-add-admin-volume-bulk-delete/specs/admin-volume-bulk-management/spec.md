## ADDED Requirements

### Requirement: Page-scoped admin volume selection
Afterglow SHALL let an administrator select individual volumes or every volume on the currently loaded all-volumes page, and SHALL clear that selection when the page, page size, filter set, or admin project scope changes.

#### Scenario: Select all on the current page
- **WHEN** an administrator activates the all-selection checkbox on a loaded volume page
- **THEN** every row on that page becomes selected and the shared bulk-action overlay reports the selected count

#### Scenario: Change the result boundary
- **WHEN** an administrator changes a filter, page, page size, or project scope after selecting volumes
- **THEN** Afterglow clears the previous page selection before presenting the new result boundary

### Requirement: Confirmed partial-success bulk deletion
Afterglow SHALL require confirmation before bulk volume deletion, SHALL process at most 50 unique volume IDs in request order without stopping after an individual failure, and SHALL return one success or failure result for every requested ID.

#### Scenario: Some selected volumes cannot be deleted
- **WHEN** the administrator confirms deletion and Cinder accepts some volume deletions but rejects others
- **THEN** Afterglow reports both counts, removes successful IDs from selection, retains failed IDs, and refreshes the current list and status summary

#### Scenario: Invalid bulk request
- **WHEN** a caller submits no volume IDs, duplicate IDs, or more than 50 IDs
- **THEN** the admin API rejects the request without deleting any volume

#### Scenario: Non-administrator requests bulk deletion
- **WHEN** a non-administrator calls the bulk volume deletion endpoint
- **THEN** Afterglow returns `403 Forbidden` without calling Cinder

### Requirement: Data-driven status filter visibility
Afterglow SHALL show the total-volume filter and only status filters whose latest cluster-wide count is greater than zero.

#### Scenario: Summary contains absent known states
- **WHEN** the status summary omits a known status or reports its count as zero
- **THEN** the status card and status-select option for that state are not rendered

#### Scenario: Active state becomes empty
- **WHEN** a refreshed status summary no longer contains the currently active status with a positive count
- **THEN** Afterglow resets the active filter to total and reloads the first result page