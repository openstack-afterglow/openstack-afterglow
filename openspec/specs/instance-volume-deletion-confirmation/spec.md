# instance-volume-deletion-confirmation Specification

## Purpose
TBD - created by archiving change require-instance-volume-deletion-confirmation. Update Purpose after archive.
## Requirements
### Requirement: Acknowledge automatic volume deletion
The UI SHALL show attached automatic-deletion volumes and require the exact displayed localized deletion word before confirming instance deletion.
#### Scenario: Automatic deletion enabled
- **WHEN** an attached volume has delete_on_termination enabled
- **THEN** empty or incorrect input cannot confirm and exact input permits explicit confirmation
#### Scenario: No automatic deletion
- **WHEN** no attached volume has automatic deletion enabled
- **THEN** ordinary confirmation requires no typed word
#### Scenario: Cancellation
- **WHEN** the user cancels and reopens
- **THEN** no deletion occurs and previous input is cleared
#### Scenario: Every deletion surface checks current attachment policy
- **WHEN** detail, single-row or bulk deletion is requested by a consumer or administrator
- **THEN** each selected instance's attachment policy is freshly read and any automatic-deletion volume requires the localized word
#### Scenario: Policy cannot be checked
- **WHEN** attachment lookup fails or a deletion flag is missing or not boolean
- **THEN** deletion is blocked rather than treating the volume as retained

