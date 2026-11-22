## MODIFIED Requirements

### Requirement: Provider-first model registry browsing
The administrator model settings MUST group registered models under tabs for AI providers that have registered models. Within a provider tab, model kinds MUST appear as independently toggleable filters. Multiple model kinds MAY be visible at once. Changing filters MUST NOT change model records, pricing, activation, or provider configuration.

#### Scenario: Filter registered models by provider and kind
- **WHEN** an administrator selects a provider tab and toggles model-kind filters
- **THEN** the page displays only registered models for that provider and selected kinds
- **AND** model kinds can be selected in combination

### Requirement: No duplicate full catalog panel
The administrator model settings MUST NOT display the full native model catalog as a separate top-level panel. Existing model discovery and catalog-backed pricing workflows MUST remain available.

#### Scenario: Register or price a catalog model
- **WHEN** an administrator uses existing model discovery or pricing controls
- **THEN** catalog-backed registration and pricing continue to work without the top-level catalog panel
