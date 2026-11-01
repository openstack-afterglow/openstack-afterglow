## ADDED Requirements

### Requirement: One authored pending visual across interface scales

The interface SHALL use the approved Afterglow glyph rain, analytic ring and reflection renderer for every indeterminate loading location. Full-area and bounded sections SHALL retain the exact authored scene; compact controls SHALL use a static frame from that same renderer rather than another spinner, dots, shimmer skeleton or approximate symbol.

#### Scenario: Initial page or panel data is unavailable
- **WHEN** a page or detail panel is waiting for its initial required data
- **THEN** its loading region fills the available owner area with the authored scene and existing localized task copy, without an unrelated artwork card or spinner

#### Scenario: A narrow control is pending
- **WHEN** a lookup, row action, refresh control or button is waiting
- **THEN** its authored compact frame remains inline and preserves valid button/span/table nesting and the existing action/disabled semantics

### Requirement: Pending decoration never invents work or outcomes

The interface SHALL retain existing request/state/authority boundaries and SHALL NOT fabricate progress, completion, elapsed duration, a minimum delay or an automatic retry. Actual progress values, observed stages, error/unknown/empty distinctions and recovery controls SHALL remain observable.

#### Scenario: Actual percentage is unavailable
- **WHEN** an active operation has no finite observed percentage
- **THEN** its progressbar omits aria-valuenow and uses authored pending artwork without a guessed fill

#### Scenario: Work settles or fails
- **WHEN** the owner reports completion, cancellation or failure
- **THEN** pending repetition stops and the existing actual result or recovery state is displayed

#### Scenario: Loaded content refreshes in the background
- **WHEN** a background refresh starts while valid same-scope data or drafts are already shown
- **THEN** those contents remain and pending artwork is limited to the refreshing control or unavailable dependent region

### Requirement: Accessible theme-aware and bounded rendering

The renderer SHALL follow current semantic theme colors live, keep canvas decoration hidden from assistive technology, and retain actual DOM task copy and recovery when canvas is unavailable. Area labels SHALL use the same analytic ring center and a radius-bounded text width. Animated scenes SHALL retain the 24fps/DPR1.5/2.4-million-backing-pixel caps, suspend when hidden/offscreen/reduced-motion/settled, and release frames, observers and listeners on destruction. Compact frames SHALL allocate no animation loop.

#### Scenario: Theme changes while loading
- **WHEN** the root theme or semantic palette changes while an area or compact loading state is mounted
- **THEN** its cached palette is refreshed and its current/static frame repaints without reading styles on every animation frame

#### Scenario: Reduced motion or forced colors applies
- **WHEN** the browser requests reduced motion or forced colors
- **THEN** actual task copy remains readable, animation stops for reduced motion, and forced colors hides canvas ornament without replacing it with another ring

### Requirement: Clean primitive cutover

All internal callers SHALL migrate to LoadingState before LoadingSpinner, LoadingSkeleton, ActivityIndicator and their exports are removed. The implementation SHALL retain independently useful behavior tests and remove obsolete structure-only assertions without adding permanent wiring or appearance tests.

#### Scenario: Retired components are removed
- **WHEN** the unified loading cutover is complete
- **THEN** no internal caller imports a retired loading primitive and no compatibility alias preserves its old visual/API
