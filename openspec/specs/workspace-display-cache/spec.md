# workspace-display-cache Specification

## Purpose
TBD - created by archiving change optimize-workspace-directory-cache. Update Purpose after archive.
## Requirements
### Requirement: Scoped browser display reuse
The resource chooser SHALL reuse bounded, unexpired successful display snapshots within the same browser session and verified logical owner, without persisting credentials or treating displayed capabilities as authority.

#### Scenario: Warm chooser reopen or reload
- **WHEN** the same verified owner opens the chooser with an unexpired stored snapshot
- **THEN** the directory and matching workspace display are available without a blocking full reload

#### Scenario: Owner or authority changes
- **WHEN** logout, new login, scope transition or permission context change invalidates the owner
- **THEN** previous display data and late responses cannot populate the new owner's chooser

### Requirement: Authorized backend display cache
The backend SHALL reduce repeated expensive directory display work with bounded caching while maintaining current native authorization before cache delivery.

#### Scenario: Warm authorized read
- **WHEN** a caller repeats an ordinary directory read under unchanged verified authority
- **THEN** cached display data can avoid redundant hydration

#### Scenario: Explicit refresh or revoked access
- **WHEN** the caller explicitly refreshes or no longer has native access
- **THEN** the cache does not bypass the fresh-read request or current authorization failure

### Requirement: Cache failures preserve correctness
Storage failures, malformed entries, expired entries and unsuccessful responses SHALL NOT become successful cached inventory or extend the usable cache lifetime.

#### Scenario: Storage unavailable
- **WHEN** browser storage or backend cache is unavailable
- **THEN** the chooser uses its authoritative read path without fabricated inventory

