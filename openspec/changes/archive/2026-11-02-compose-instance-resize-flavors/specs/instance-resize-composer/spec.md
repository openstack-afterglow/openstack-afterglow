## ADDED Requirements

### Requirement: Instance-scoped resize composition
User and administrator instance detail SHALL offer resize for ACTIVE and SHUTOFF instances through direct composition, previously selected compositions and the existing native catalog. The backend SHALL validate current authority and exact instance project, charge incremental quota relative to its current flavor, reject unchanged shape and image-backed root-disk shrink, and retain unknown-publication blocking.

#### Scenario: Running instance resize
- **WHEN** an authorized user selects a different eligible flavor for an ACTIVE instance
- **THEN** the interface warns about guest restart and requests explicit confirmation before submitting one resize.

#### Scenario: Native accepts but status refresh fails
- **WHEN** the resize request succeeds and the subsequent detail refresh fails
- **THEN** the dialog closes and the existing instance remains visible with a refresh warning rather than inviting resubmission.

#### Scenario: Current authority or quota changed
- **WHEN** saving or submitting a composition after authority, instance state or quota changed
- **THEN** the backend performs fresh validation and rejects unavailable or unauthorized changes without bypassing native policy.
