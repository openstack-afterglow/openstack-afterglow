## ADDED Requirements

### Requirement: Character status marks distinguish in-flight from settled

Compact in-flight indicators SHALL rotate the character spinner, and settled statuses SHALL show a static mark. Only success and failure SHALL be implied by tone; canceled or permission marks SHALL appear only when the status map declares that outcome, and all other states SHALL use a neutral mark.

#### Scenario: Unknown or observed status
- **WHEN** a StatusChip shows an observed, stopped, unavailable or unknown native status
- **THEN** it shows the neutral mark and never a canceled, failed or permission mark

#### Scenario: Reduced motion
- **WHEN** motion is reduced
- **THEN** the spinner stays on a frame that is not any settled mark
