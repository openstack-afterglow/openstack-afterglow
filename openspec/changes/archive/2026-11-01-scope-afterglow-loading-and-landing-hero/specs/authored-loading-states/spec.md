## MODIFIED Requirements

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

### Requirement: Accessible theme-aware and bounded rendering

Animated full scenes SHALL follow live theme colors, keep decoration hidden from assistive technology, retain the 24fps/DPR1.5/2.4-million-pixel caps and suspend when hidden, offscreen, reduced-motion or settled. Character indicators SHALL share one step clock that stops without subscribers, while hidden, or under reduced motion, and SHALL render decorative characters as aria-hidden generated content.

#### Scenario: Reduced motion or forced colors applies
- **WHEN** the browser requests reduced motion or forced colors
- **THEN** copy remains readable, character and scene animation stops, and forced colors uses system text color

## ADDED Requirements

### Requirement: Landing first screen uses the authored scene

The public main page first screen SHALL present the authored Afterglow scene with the product wordmark, actual localized lead copy and console/explore actions, a visible motion pause/play control, and a soft light that follows a mouse pointer. Touch input SHALL NOT trigger the light, and pointer listeners and frames SHALL be released on destruction.

#### Scenario: Mouse moves over the first screen
- **WHEN** a mouse pointer moves inside the hero
- **THEN** glyphs near the pointer brighten and fade when the pointer leaves, including while the scene is paused
