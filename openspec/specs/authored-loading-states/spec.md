# authored-loading-states Specification

## Purpose
TBD - created by archiving change unify-authored-loading-states. Update Purpose after archive.
## Requirements
### Requirement: One authored pending visual across interface scales

The interface SHALL reserve the animated authored Afterglow glyph scene for loading that occupies a whole page, panel or large primary list. Smaller pending regions SHALL use the character-interface family from `output/afterglow-loading/progress.html`: a character flow bar without percentage for cards/sections, column-preserving character rows for tables, and a `[~]` status glyph for rows, buttons and pickers. Pending decoration SHALL NOT repeat the full scene inside individual cards, tables or controls.

#### Scenario: Initial page or panel data is unavailable
- **WHEN** a page or detail panel is waiting for its initial required data
- **THEN** its loading region fills the available owner area with the authored scene and existing localized task copy

#### Scenario: A card or table is pending inside a loaded page
- **WHEN** a subordinate card waits for data, or a table body waits for its rows
- **THEN** it shows the character flow bar or column-preserving character rows with the owner's localized copy, without an artwork canvas

#### Scenario: A narrow control is pending
- **WHEN** a lookup, row action, refresh control or button is waiting
- **THEN** a `[~]` glyph precedes the existing copy, preserving valid nesting, action/disabled semantics and the copy as the visible/accessible text

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

Animated full scenes SHALL follow live theme colors, keep decoration hidden from assistive technology, retain the 24fps/DPR1.5/2.4-million-pixel caps and suspend when hidden, offscreen, reduced-motion or settled. Character indicators SHALL share one step clock that stops without subscribers, while hidden, or under reduced motion, and SHALL render decorative characters as aria-hidden generated content.

#### Scenario: Reduced motion or forced colors applies
- **WHEN** the browser requests reduced motion or forced colors
- **THEN** copy remains readable, character and scene animation stops, and forced colors uses system text color

### Requirement: Clean primitive cutover

All internal callers SHALL migrate to LoadingState before LoadingSpinner, LoadingSkeleton, ActivityIndicator and their exports are removed. The implementation SHALL retain independently useful behavior tests and remove obsolete structure-only assertions without adding permanent wiring or appearance tests.

#### Scenario: Retired components are removed
- **WHEN** the unified loading cutover is complete
- **THEN** no internal caller imports a retired loading primitive and no compatibility alias preserves its old visual/API

### Requirement: Landing first screen uses the authored scene

The public main page first screen SHALL present the authored Afterglow scene with the product wordmark, actual localized lead copy and console/explore actions, a visible motion pause/play control, and a soft light that follows a mouse pointer. Touch input SHALL NOT trigger the light, and pointer listeners and frames SHALL be released on destruction.

#### Scenario: Mouse moves over the first screen
- **WHEN** a mouse pointer moves inside the hero
- **THEN** glyphs near the pointer brighten and fade when the pointer leaves, including while the scene is paused

### Requirement: Landing service sections explain themselves visually

Each landing service section SHALL show a large, product-like scene with icons, localized labels and illustrative values that reads from inputs to the resulting research resource, rather than decorative character art. The scene SHALL keep a localized accessible name, play its motion once when visible, end in a completed state, and present that complete static frame under reduced motion.

#### Scenario: Visitor scrolls to a service section
- **WHEN** a service section scrolls into view
- **THEN** its stages appear in order with their resources and states, and the motion settles on the completed scene

### Requirement: Panel surface loading fills its panel

A surface loading scene used for a whole panel SHALL fill the panel height remaining below the panel controls, and a caller-provided minimum height SHALL take precedence over the default minimum.

#### Scenario: Instance detail panel opens
- **WHEN** the instance detail slide panel is loading its instance for the first time
- **THEN** the authored scene extends from below the refresh controls to the bottom of the panel without adding scroll

### Requirement: Character status marks distinguish in-flight from settled

Compact in-flight indicators SHALL rotate the character spinner, and settled statuses SHALL show a static mark. Only success and failure SHALL be implied by tone; canceled or permission marks SHALL appear only when the status map declares that outcome, and all other states SHALL use a neutral mark.

#### Scenario: Unknown or observed status
- **WHEN** a StatusChip shows an observed, stopped, unavailable or unknown native status
- **THEN** it shows the neutral mark and never a canceled, failed or permission mark

#### Scenario: Reduced motion
- **WHEN** motion is reduced
- **THEN** the spinner stays on a frame that is not any settled mark

### Requirement: Landing presents Lumen as an LLM gateway and Afterglow MCP

The landing page SHALL present Lumen as an LLM gateway connecting multiple providers to researchers coding agents, and SHALL present Afterglow MCP as letting agents inspect and manage cloud resources, each with a localized motion scene following the shared scene lifecycle.

#### Scenario: Visitor reaches the Lumen section
- **WHEN** the gateway and MCP sections scroll into view
- **THEN** providers flow through Lumen to Claude Code and Codex, and an agent calls Afterglow MCP tools that update a research-cloud VM, each settling on its completed frame

