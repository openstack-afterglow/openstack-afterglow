# instance-deletion-policy-freshness Specification

## Purpose
TBD - created by archiving change fix-instance-deletion-policy-freshness. Update Purpose after archive.
## Requirements
### Requirement: Fresh attachment policy
The consumer attachment endpoint SHALL honor refresh=true and cache=false so deletion preflight cannot use stale retained-volume policy.
#### Scenario: External policy change
- **WHEN** a cached false policy changes to true at origin
- **THEN** a refresh or cache bypass returns true

