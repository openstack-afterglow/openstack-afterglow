## Why

The provider cards emphasize current-period usage, so administrators cannot quickly distinguish spend already incurred from credit that is still available or was purchased. Provider APIs expose different financial data, so the page must surface authoritative balance data where available and an explicit no-API state instead of implying that usage can be converted into a balance.

## What Changes

- Add a persistent account-credit section to every configured provider card, separate from Lumen-attributed and official organization usage.
- Show provider-reported credit values with exact provenance: OpenRouter API-key remaining limit, and DeepSeek total, purchased, and granted balances.
- Mark OpenAI, Anthropic, Gemini, and other portal-only providers as not exposing account balance through the configured official API rather than estimating remaining credit from usage.
- Keep the provider's trusted HTTPS billing action adjacent to the credit state so administrators can inspect or purchase credit in the official console.
- Preserve the existing bulk billing request, credential boundaries, usage reporting, provider CRUD, and failure isolation.

## Capabilities

### New Capabilities
- `provider-account-credit-visibility`: Truthful, responsive display of authoritative provider credit state and explicit provider-API limitations in administrator settings.

### Modified Capabilities

None.

## Impact

Affects `frontend/src/lib/components/admin/chat/ChatConfiguration.svelte`, focused administrator provider tests, `docs/api/chat.md`, `ARCHITECTURE.md`, and `CHANGELOG.md`. The existing Lumen bulk billing response remains authoritative and requires no new secret, provider request, database state, or Afterglow backend endpoint.
