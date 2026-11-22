## ADDED Requirements

### Requirement: Image selection readiness errors identify the first controller and earlier failures
When image reference selection is incomplete, the readiness assertion SHALL identify the first targeted controller. If that controller is no longer an active host in the play, the message SHALL explain that the assertion may be secondary and direct the operator to inspect that controller's earlier fatal output. Selection behavior and fail-closed handling SHALL remain unchanged.

#### Scenario: The first targeted controller failed before image selection
- **WHEN** a remaining controller reaches the readiness assertion and the first targeted controller is absent from the active play host list
- **THEN** the error identifies the first controller, explains that the failure may be secondary, and directs the operator to the first fatal output

#### Scenario: Selection fails while the first controller remains active
- **WHEN** the readiness assertion fails and the first targeted controller remains active in the play
- **THEN** the error identifies the first controller and retains the unresolved/stale/other-service refusal without claiming a prior failure
