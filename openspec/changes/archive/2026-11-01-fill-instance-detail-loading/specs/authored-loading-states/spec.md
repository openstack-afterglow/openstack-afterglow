## ADDED Requirements

### Requirement: Panel surface loading fills its panel

A surface loading scene used for a whole panel SHALL fill the panel height remaining below the panel controls, and a caller-provided minimum height SHALL take precedence over the default minimum.

#### Scenario: Instance detail panel opens
- **WHEN** the instance detail slide panel is loading its instance for the first time
- **THEN** the authored scene extends from below the refresh controls to the bottom of the panel without adding scroll
