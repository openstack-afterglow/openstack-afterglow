## Why

The API-key connection guide labels `ANTHROPIC_BASE_URL=<legacy custom gateway> claude` as Claude Code device authorization. Claude Code 2.1.278 does not discover or authenticate that private protocol: current Claude Apps Gateway login requires administrator-managed settings plus the official OAuth discovery/refresh protocol. The supported Lumen path is the ordinary Anthropic Messages endpoint with a Lumen API key.

## What Changes

- Replace the unsupported device-authorization command with a direct Claude Code API-key configuration using the discovered Anthropic SDK base URL.
- Keep the API key in `LUMEN_API_KEY`, map the selected public model ID to Claude Code's model variables, and document optional provider routing.
- Correct API documentation so the legacy Lumen device endpoints are not presented as current Claude Code support.
- Update focused tests and architecture evidence.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `chat-api-key-management`: the connection guide emits a runtime-verified Claude Code direct API-key setup and does not claim unsupported native Gateway login.

## Impact

The chat API-key guide, focused component assertions, chat API documentation, and architecture review record change. API-key creation and legacy server endpoints are unchanged.
