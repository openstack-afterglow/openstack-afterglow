## ADDED Requirements

### Requirement: Member-search overlays follow the active theme
The admin group member-search result panel and no-results panel SHALL use shared semantic surface, ink, border, and elevation styling that resolves from the active application theme. They MUST NOT force a dark-only background value.

#### Scenario: Matching users in light mode
- **WHEN** an administrator searches for a user while the application uses the light theme and matching users are available
- **THEN** the result panel uses a light raised surface with readable result text and add action

#### Scenario: No matching users in light mode
- **WHEN** an administrator searches for a user while the application uses the light theme and no users match
- **THEN** the empty result panel uses a light raised surface with readable empty-state text

#### Scenario: Matching users in dark mode
- **WHEN** an administrator searches for a user while the application uses the dark theme
- **THEN** the result panel remains a dark raised surface with readable result text and add action

### Requirement: Active GroupCard content remains readable in both themes
Active group descriptions, identifiers, member emails, loading and empty messages, destructive actions, error messages, and the add-member action SHALL use semantic design-system colors or shared primitives that provide readable light- and dark-theme states. Disabled-only ink SHALL NOT be used for active metadata.

#### Scenario: Group and member metadata in light mode
- **WHEN** an expanded group card is rendered in the light theme
- **THEN** its description, identifier, member email, loading or empty copy, and destructive controls use readable semantic colors

#### Scenario: Add-member action in either theme
- **WHEN** an eligible user appears in the member-search result panel
- **THEN** the add action uses the shared primary Button behavior with readable text, hover, focus, and disabled states

#### Scenario: Destructive and error states in either theme
- **WHEN** delete, remove, or add-member error content is shown
- **THEN** it uses the semantic danger tone rather than raw palette classes

### Requirement: Member-search behavior remains unchanged
The theme correction SHALL preserve existing member exclusion, case-insensitive name filtering, result limit, add-member action, and overlay geometry.

#### Scenario: Search and add after theme correction
- **WHEN** an administrator enters a partial user name and selects an eligible result
- **THEN** the existing add-member callback runs for that user and successful completion clears the search text
