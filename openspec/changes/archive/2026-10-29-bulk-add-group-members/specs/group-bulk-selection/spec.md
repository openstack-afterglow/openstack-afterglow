## ADDED Requirements

### Requirement: Browse and select group candidates
The administrator interface SHALL present the available candidates for the selected source before search, support filtering by existing identity fields, and allow selecting individual users or all visible matches.

#### Scenario: Browse without a query
- **WHEN** the candidate directory has loaded successfully
- **THEN** available nonmembers appear without requiring a search

### Requirement: Safely add selected users
The interface SHALL submit selected users through existing authorized membership operations, stop on failure or scope change, and retain unsubmitted selections within the same scope.

#### Scenario: Partial failure
- **WHEN** one selected addition fails
- **THEN** later additions are not dispatched and previously successful additions remain intact
