# standalone-auth-studio Specification

## Purpose
TBD - created by archiving change unify-standalone-auth-studio. Update Purpose after archive.
## Requirements
### Requirement: Consistent independent entry surfaces
All independent account/authentication and OAuth consent pages SHALL use the approved shared studio shell while preserving existing API contracts, authority, one-use token behavior and localized states.

#### Scenario: Account and recovery entry
- **WHEN** a user opens signup, recovery, verification, invitation, provider callback or workspace selection
- **THEN** the page presents shared branding, locale/theme and responsive artwork/form composition
- **AND** all loading, failure, approval, completion and identity details remain reachable.

#### Scenario: Real OAuth consent
- **WHEN** a user reviews MCP or Claude access
- **THEN** real client, callback, requested access, deadlines and every authorized project option remain visible/reachable
- **AND** the existing grant/deny and scope authority checks remain unchanged.

#### Scenario: Constrained viewport
- **WHEN** available height cannot contain the form or security details
- **THEN** decorative artwork yields first and the panel scrolls safely without clipping its beginning or actions.

#### Scenario: Switching language during a one-use flow
- **WHEN** the user switches locale after a username link has been inspected, an account result returned, or a provider/consent ticket loaded
- **THEN** translated markup updates without remounting the entry route
- **AND** the existing result, ticket and explicit choices remain in memory without replaying an inspection or mutation.
