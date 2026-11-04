## ADDED Requirements

### Requirement: Configurable Kolla backend workers

The Kolla role SHALL expose `afterglow_backend_workers` as a positive decimal integer, defaulting to one, and pass it to the existing Uvicorn factory command on each backend host.

#### Scenario: Default count
- **WHEN** the operator does not set the worker count
- **THEN** the command starts one Uvicorn worker with existing proxy behavior

#### Scenario: Configured count
- **WHEN** the operator configures a positive worker count
- **THEN** the rendered Uvicorn command uses that count

#### Scenario: Invalid count
- **WHEN** the count is zero, negative, nonintegral, boolean, or not decimal
- **THEN** configuration and activation fail before launching the backend
