## MODIFIED Requirements

### Requirement: Claude Code connection guidance

The API-key settings surface MUST build Claude Code guidance from the discovered Anthropic SDK base URL. It MUST use an ordinary Lumen API key as `ANTHROPIC_AUTH_TOKEN`, use the selected public model ID for Claude Code model variables, and MUST NOT embed a browser token or claim the legacy custom device endpoints are supported by the current Claude Code login protocol.

#### Scenario: User copies Claude Code setup

- **WHEN** authenticated discovery returns an Anthropic SDK base URL
- **THEN** the guide shows and copies a shell configuration that sets `ANTHROPIC_BASE_URL` to that exact URL, reads the credential from `LUMEN_API_KEY`, maps `LUMEN_MODEL`, and launches `claude`

#### Scenario: Public model ID has multiple providers

- **WHEN** the user needs an explicit provider route
- **THEN** the guide documents `ANTHROPIC_CUSTOM_HEADERS` with `X-Lumen-Provider` as an optional environment variable rather than hard-coding a provider

#### Scenario: Legacy device protocol is present in discovery

- **WHEN** discovery also returns the legacy Lumen gateway base URL
- **THEN** the current Claude Code guide ignores it and does not advertise native device authorization
