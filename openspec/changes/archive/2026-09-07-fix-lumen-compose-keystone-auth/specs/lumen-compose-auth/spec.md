## ADDED Requirements

### Requirement: Consistent Lumen Keystone configuration

The local Compose stack MUST provide Lumen migrate, API, and worker processes with identical Keystone authority settings. Explicit `LUMEN_KEYSTONE_*` values MUST take precedence over existing `OS_*` fallbacks, and the stack MUST NOT invent localhost authentication defaults.

#### Scenario: Explicit Lumen settings are present

- **WHEN** an operator supplies `LUMEN_KEYSTONE_AUTH_URL`, username, password, project name, and domain values
- **THEN** every Lumen process receives those values through its canonical `KEYSTONE_*` environment variables

#### Scenario: Authority settings are missing

- **WHEN** neither an explicit Lumen value nor its supported OpenStack fallback exists
- **THEN** Lumen receives no fabricated local authority and authentication fails closed

### Requirement: Deterministic separated-service environment loading

The documented local startup command MUST load `.env` before `docker-compose.services.env` and MUST activate the `services` profile.

#### Scenario: Operator starts the documented Lumen stack

- **WHEN** the operator runs the documented dual env-file Compose invocation for the Lumen services
- **THEN** migration completes and both the API and worker start with the resolved service configuration

### Requirement: Distinct trusted project scopes

Afterglow MUST forward the verified Keystone connection project separately from an authorized logical target project and MUST NOT forward a browser-provided target-project header.

#### Scenario: System administrator delegates to another project

- **WHEN** a verified system administrator selects a logical project different from the token connection project
- **THEN** the BFF sends the connection project as `X-Project-Id` and the authorized logical project as `X-Target-Project-Id`

#### Scenario: Browser supplies a target header

- **WHEN** a browser request includes its own target-project header
- **THEN** the BFF ignores that value and derives all forwarded project scope from verified server-side state
