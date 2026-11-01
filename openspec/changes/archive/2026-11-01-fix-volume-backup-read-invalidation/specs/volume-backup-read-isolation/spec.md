## ADDED Requirements

### Requirement: Policy listing is an isolated read

The application SHALL expose project-scoped volume-backup policy listing via GET and SHALL NOT invalidate concurrent source-volume or backup reads merely by listing policies. The application SHALL retain mutation invalidation for policy changes and preserve native authorization and project ownership checks.

#### Scenario: Concurrent backup page hydration
- **WHEN** policy listing, source-volume listing and backup listing return success concurrently
- **THEN** the real browser client publishes all three reads without mutation-induced AbortError

#### Scenario: Reader policy access
- **WHEN** a project reader requests policy listing
- **THEN** GET succeeds subject to the existing scope boundaries, while create/update/delete remain denied

### Requirement: Failure is not successful empty state

The backup page SHALL distinguish a failed list from a successful list containing no backups.

#### Scenario: Backup list failure
- **WHEN** backup listing fails with no previous rows
- **THEN** the alert is visible without successful-empty artwork or pending loading state
