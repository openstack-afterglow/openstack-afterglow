## ADDED Requirements

### Requirement: Recover invalidated group inventory read
When a current-scope group inventory read is invalidated by a concurrent mutation, the group page SHALL perform at most one fresh scoped read instead of reporting the invalidated result as a provider failure. A real replacement failure SHALL remain visible.

#### Scenario: Concurrent membership update
- **WHEN** a group list read is invalidated while adding a member
- **THEN** the controller requests the current group list again without accepting the stale response
