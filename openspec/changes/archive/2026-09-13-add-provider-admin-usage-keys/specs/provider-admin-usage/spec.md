## ADDED Requirements

### Requirement: Administrator billing credential flow
Afterglow SHALL allow an administrator to set or remove a separate masked billing administrator key only for direct OpenAI API and Anthropic API providers, and SHALL never receive the stored key in a read response.

#### Scenario: Administrator configures a billing key
- **WHEN** an administrator submits a non-empty administrator key from a provider row
- **THEN** Afterglow sends it once to the provider PATCH endpoint and subsequently displays only the configured state

#### Scenario: Administrator removes a billing key
- **WHEN** an administrator explicitly removes the configured key
- **THEN** Afterglow submits null and returns the provider to the missing-administrator-key state

### Requirement: Distinct organization usage scope
Afterglow SHALL render provider organization usage separately from Lumen-attributed usage and SHALL identify providers without a compatible programmatic API accurately.

#### Scenario: Organization data is available
- **WHEN** Lumen returns OpenAI or Anthropic organization metrics
- **THEN** the row shows provider-reported current-day, current-week, and current-month metrics without presenting them as Lumen-only spend

#### Scenario: Provider has no compatible API
- **WHEN** the provider is Gemini or Perplexity API Platform
- **THEN** the row directs the administrator to the official console and explains the programmatic limitation without requesting a misleading credential

### Requirement: Fresh post-mutation billing state
Afterglow SHALL issue a fresh billing request after credential mutation and prevent superseded requests from publishing stale state.

#### Scenario: Old request completes after key update
- **WHEN** a billing request started before an administrator-key update completes after the fresh post-update request
- **THEN** only the fresh response may remain visible
