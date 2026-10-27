## ADDED Requirements

### Requirement: Authenticated checks work on a fresh toolbox

When Cloud Shell or Manila is enabled, Kolla MUST prepare the authenticated toolbox cloud before any dependent CLI check. The Manila client MUST be installed only when Manila is enabled.

#### Scenario: Cloud Shell without prior Manila execution
- **WHEN** Cloud Shell is enabled and the toolbox has no existing cloud configuration
- **THEN** its authenticated precheck receives the configured Kolla cloud regardless of whether Manila is enabled.

### Requirement: Standard reconfiguration selects current application images

With no explicit application image pin, the standard full-inventory Kolla reconfigure MUST resolve each enabled application image's published channel once per invocation and apply that immutable selection to its targets. Explicit rollback pins and datastore image settings MUST remain supported.

#### Scenario: Published channel advances
- **WHEN** a subsequent untagged reconfigure starts after a channel changes
- **THEN** it selects the new published digest without requiring extra flags.
