## ADDED Requirements

### Requirement: Dashboard trend interaction
The user overview SHALL expose Bklit tooltip and accessible ordered values for available trend data, without inventing observation timestamps absent from the API.

#### Scenario: Inspect a measured sample
- **WHEN** an available trend has measured values
- **THEN** the chart exposes the value and sample order via tooltip and accessible data disclosure

### Requirement: Documentation navigation
The user sidebar SHALL omit the duplicated Docs link while the header Docs link remains accessible on mobile and desktop.

#### Scenario: Open documentation from a narrow viewport
- **WHEN** a user opens the dashboard on a mobile viewport
- **THEN** the header provides a visible link to Docs
