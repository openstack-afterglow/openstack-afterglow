## Why

The provider billing page can only show provider-reported data for inference-key endpoints. OpenAI and Anthropic publish organization usage and cost APIs, but those endpoints require separate administrator credentials, so treating the inference key as sufficient produces an unsupported state. The current production screenshot also shows HTTP 405 because the Afterglow frontend has reached the bulk route before the matching Lumen backend was deployed.

## What Changes

- Extend provider settings with a masked administrator billing-key flow for direct OpenAI API and Claude API providers.
- Keep inference and administrator credentials visibly and operationally separate.
- Show provider-reported current-day, current-week, and current-month organization cost/usage when Lumen returns it.
- Preserve local Lumen-attributed usage beside organization-wide provider data so the scopes cannot be confused.
- Explain that Gemini exposes balance and usage through AI Studio only, and that Perplexity's documented Computer Analytics API does not represent API Platform/Sonar billing.
- Force a fresh, generation-fenced billing reload after credential mutation so an older in-flight snapshot cannot overwrite the new-key result.

## Capabilities

### New Capabilities
- Secure provider administrator billing-key configuration from the web console.
- Organization-reported OpenAI and Anthropic usage/cost visualization.

### Modified Capabilities
- Provider billing states distinguish missing administrator credentials, unsupported programmatic APIs, partial provider data, and live organization data.

## Impact

Changes the administrator chat provider UI, response contracts, focused tests, design documentation, chat API documentation, and architecture review. No administrator key is exposed to the browser after submission. Deployment must roll compatible Lumen and Afterglow revisions together to avoid the observed bulk-route HTTP 405 version skew.
