# console-workspaces Specification

## Purpose
Separate user workspace membership from global administrator observation and preserve native Personal project identity while exposing an owner-editable human display label.

## Requirements

### Requirement: User-console workspace authority is actual membership
The user-facing domain/project directory, cached display snapshots, explicit scope commits and remembered-workspace restoration SHALL use actual enabled native domain/project membership for both ordinary users and system administrators. Global administration SHALL remain separate and SHALL NOT grant user-console membership. Immutable account-home metadata SHALL remain in authentication security context but SHALL NOT be displayed in the resource chooser.

#### Scenario: Administrator opens the user console
- **WHEN** an administrator has one Personal project and no membership in other observed domains/projects
- **THEN** the user directory/chooser exposes only authorized workspaces and a manually submitted or stale nonmember target is denied before native exchange

#### Scenario: Remembered administrator target loses membership
- **WHEN** a fresh login restores an opted-in workspace with no current membership
- **THEN** it lands in the verified owned Personal primary rather than retaining the target through system-admin observation authority

### Requirement: Administrator chrome has no global workspace chooser
Administrator header and navigation drawer SHALL omit the global workspace selector at every supported breakpoint. Mode switching and independent administrator inventory/target filters SHALL remain available. User-mode navigation, project management and shared-resource actions SHALL use user project authority rather than add controls from a system-admin identity flag.

#### Scenario: Administrator changes surface or viewport
- **WHEN** the user enters an administrator route on mobile, tablet or desktop
- **THEN** neither header nor drawer offers a global domain/project switcher while the equivalent user surface still reaches its authorized chooser

### Requirement: Personal owner may edit persistent display name without renaming identity
The verified current Personal owner SHALL be able to save a trimmed1–64-codepoint human-facing label in `afterglow_display_name`, including a direct native member owner or verified historical unique owner. The generated native project name, UUID, ownership/enrollment markers, other extras, credentials, grants, quotas and resources SHALL remain unchanged. Extra fields, controls, ambiguous provenance, foreign owners, stale/revoked authority and substituted/unconfirmed native responses SHALL fail closed. Successful native readback SHALL precede user-facing label publication in lists/header/fresh login, and late owner/scope/readiness/logout/ABA results SHALL NOT publish or replay.

#### Scenario: Ordinary Personal member owner saves readable label
- **WHEN** the real owner submits a valid label through user project settings
- **THEN** one bounded metadata PATCH is read back, the existing project identity is preserved and the new label appears in the current header/chooser and next login

#### Scenario: Global administrator tries another person's Personal project
- **WHEN** the administrator identity lacks exact current Personal ownership and membership
- **THEN** label access/update is denied without acquiring a writer or changing native identity/grants
