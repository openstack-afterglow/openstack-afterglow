# Proposal: Codex Lumen connection guide

## Why

Afterglow's API-key settings showed OpenAI, Anthropic, and Claude Code connection instructions but omitted the Codex CLI even though Lumen advertises a direct Responses client endpoint. Users otherwise had to guess the provider URL and wire mode, risking the dashboard-host and credential-boundary errors that discovery is intended to prevent.

## What Changes

- Consume Lumen's advertised `clients.codex.base_url` rather than deriving a URL from the dashboard host.
- Show the required Codex `config.toml` fields for `wire_api = "responses"`, environment-backed authentication, and disabled OpenAI account authentication.
- Explain model/provider selection and the ordinary Lumen API-key boundary.
- Cover URL validation, copied configuration, and the existing responsive connection-guide surface.
- Update chat documentation and architecture evidence.

## Capabilities

### New Capabilities

- `external-chat-clients`: discovery-derived Codex Responses configuration in the authenticated API-key settings surface.

### Modified Capabilities

- None.

## Impact

The API-key settings component, focused component coverage, chat integration documentation, and architecture evidence change. Afterglow does not store the plaintext key, add a Codex-specific credential type or backend route, or claim a live external provider deployment.
