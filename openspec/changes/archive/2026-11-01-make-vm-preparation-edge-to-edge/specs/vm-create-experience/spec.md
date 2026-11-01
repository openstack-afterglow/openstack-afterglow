## ADDED Requirements

### Requirement: Preparation owns the entire VM panel surface
The VM creation preparation state SHALL display the existing authored glyph scene edge-to-edge across the available panel width and height, without preparation-only outer padding, a framed artwork card, visible external heading, or help/footer row. The loaded wizard and administrator target-selection layout SHALL retain their existing chrome and spacing. The existing accessible panel close action SHALL remain available as a 44px integrated overlay with the existing keyboard dismissal and focus lifecycle.

#### Scenario: Initial dependencies are pending
- **WHEN** the current-scope VM composer resources, GPU snapshot, history or create-capacity catalog are not ready
- **THEN** the scene fills the preparation surface, the form/stepper/progression footer are absent, and actual pending work remains readable at the exact analytic ring center

#### Scenario: Preparation completes or the user closes it
- **WHEN** the final required dependency settles successfully
- **THEN** the ordinary wizard appears with its existing heading, spacing, stepper and footer
- **WHEN** the user activates the overlay close or Escape while preparation is pending
- **THEN** the existing close lifecycle runs without issuing a cloud mutation

### Requirement: Authored scene follows live semantic appearance
The scene SHALL derive its base, glyph and status colors from the existing semantic surface/accent/ink tokens and the current light/dark appearance. Root class/style updates SHALL refresh cached canvas colors and redraw the current elapsed frame without remounting, resetting elapsed time, or reading computed styles per animation frame. The authored source assets, glyph algorithm, analytic geometry and bounded rendering cadence/storage SHALL remain unchanged.

#### Scenario: Appearance or palette changes during a pending scene
- **WHEN** the console applies a light/dark class change or root semantic palette style update
- **THEN** canvas and DOM status update in place using the same geometry and dependency state

#### Scenario: Motion is reduced or the scene is settled
- **WHEN** an appearance update arrives while animation is paused by reduced motion or settled work
- **THEN** the current static frame updates without enabling a repeating animation
- **WHEN** the component unmounts
- **THEN** RAF, palette/size/intersection observations and media/visibility listeners are released and subsequent palette changes do not redraw it

### Requirement: Full-surface preparation retains genuine accessible lifecycle state
The decorative canvas SHALL remain hidden from assistive technology. The actual first pending task SHALL remain a polite atomic DOM status at the shared analytic center; every lane SHALL retain its accessible pending/complete/failed state. Failure details and explicit retry SHALL remain reachable inside the scene without moving the status center or waiting for other busy lanes to settle. Only failed lanes SHALL retry on explicit user action, and same-scope background refresh SHALL NOT replace an already editable form. Scope/readiness loss and reopen SHALL require fresh preparation. Canvas unavailability and forced colors SHALL retain real text, errors, retry and close.

#### Scenario: A dependency fails while another remains pending
- **WHEN** one lane fails and another is still pending
- **THEN** the status names genuine pending work, the failure Alert names the failed lane, and neither live region is under an aria-busy ancestor

#### Scenario: Preparation has already completed
- **WHEN** same-scope background refresh becomes pending or fails
- **THEN** the existing editable form and draft remain mounted rather than showing preparation again

#### Scenario: Rendering is unavailable
- **WHEN** canvas context creation fails or forced colors hides decoration
- **THEN** the real status, accessible name/description, task states, explicit error/retry and integrated close remain available
