## ADDED Requirements

### Requirement: DEFAULT debug controls safe diagnostic verbosity

Afterglow SHALL accept valid TOML `[DEFAULT]` with boolean `debug = true`, default to false, and respect normal explicit environment precedence. Debug SHALL enable useful application DEBUG/source/decision logging while retaining configured log destinations, redaction and normal authenticated HTTP behavior.

#### Scenario: Valid debug enabled
- **WHEN** DEFAULT.debug is true and no environment override disables it
- **THEN** actual application diagnostic records include DEBUG verbosity and safe source context
- **AND** no token, password, key, Authorization value or raw request/body transport dump is logged

#### Scenario: Normal logging preserved
- **WHEN** DEFAULT.debug is absent or false, or an explicit environment override disables it
- **THEN** existing logging level configuration and normal behavior remain intact

#### Scenario: Invalid TOML remains invalid
- **WHEN** a configuration uses the invalid uppercase TOML boolean True
- **THEN** loading reports the parser error rather than rewriting it or silently falling back

### Requirement: Debug remains an operator diagnostic switch

Debug SHALL NOT bypass authentication/authorization, expose HTTP exception tracebacks, alter credentials, or enable unsafe third-party wire logging. Affected configuration examples and generated deployments SHALL preserve the same boolean semantics.

#### Scenario: Sensitive downstream failure
- **WHEN** an authenticated request fails and an exception contains synthetic credential sentinels
- **THEN** the debug log explains the safe failure context without those sentinels or raw credential fields
