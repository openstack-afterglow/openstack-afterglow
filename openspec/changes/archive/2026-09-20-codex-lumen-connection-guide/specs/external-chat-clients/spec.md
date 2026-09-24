## ADDED Requirements

### Requirement: Discovery-derived Codex Responses guidance

The authenticated API-key settings surface MUST offer a copyable Codex CLI custom-provider configuration using Lumen's advertised `clients.codex.base_url`. The configuration MUST select `wire_api = "responses"`, read the ordinary Lumen API key from `LUMEN_API_KEY`, disable OpenAI account authentication and websocket transport, and MUST NOT embed a plaintext credential. It MUST explain that the public model ID is copied from the model selector and that `X-Lumen-Provider` is optional only when the same public ID is ambiguous.

#### Scenario: User copies a usable Codex configuration

- **WHEN** authenticated compatibility discovery returns a valid HTTPS `clients.codex.base_url`
- **THEN** the settings surface renders that exact URL in a copyable Codex provider configuration and keeps the copy action available at mobile, tablet, and desktop widths

#### Scenario: Codex discovery URL is unavailable or unsafe

- **WHEN** compatibility discovery omits the Codex base URL or returns a URL with credentials, query parameters, or a non-HTTP(S) scheme
- **THEN** the settings surface MUST NOT publish a guessed or unsafe configuration and MUST show the existing retryable connection-information error
