# optional-default-network Specification

## Purpose
TBD - created by archiving change normalize-optional-default-network-response. Update Purpose after archive.
## Requirements
### Requirement: Default network absence is successful optional data
The default-network GET SHALL return HTTP200 with network_id:null when the database query confirms no default record. Configured records SHALL remain unchanged and storage failures SHALL remain errors.

#### Scenario: No saved default
- **WHEN** an authorized project has no saved default record
- **THEN** GET returns200 with network_id:null without native or database writes

#### Scenario: Storage fails
- **WHEN** default-network storage cannot be read
- **THEN** the endpoint returns503 rather than optional absence

