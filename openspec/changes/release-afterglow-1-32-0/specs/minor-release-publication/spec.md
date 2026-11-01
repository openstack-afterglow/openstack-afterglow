## ADDED Requirements

### Requirement: Verified minor release publication
The release SHALL publish current reviewed changes as1.32.0 on dev, after the full repository gate and changed-path smoke pass, with synchronized metadata and accurate release notes.

#### Scenario: Successful source and image publication
- **WHEN** exact pushedSHA CI succeeds
- **THEN** an immutablev1.32.0 tag and GitHub release are published and all app images are verified against that revision and their latest aliases.

#### Scenario: Existing production incident
- **WHEN** GitHub publication completes while controller1 recovery remains unqualified
- **THEN** production cutover remains blocked and notes do not claim live deployment.
