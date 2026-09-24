## Why

Lumen is adding a per-model prompt-cache ledger modeled on the Anthropic organization usage report (uncached input, cache read, cache creation 5m, cache creation 1h, output). Until an administrator sets a model's cache price, cache tokens bill at 0 USD. Afterglow's model settings could not set or show these prices, so the 0 USD billing was invisible and could not be changed.

## What Changes

- The admin model settings (`ChatConfiguration.svelte`) accept three optional, independent per-million cache prices, each a decimal string or `null`: `cache_read_price_per_million`, `cache_write_price_per_million` (5-minute write), and `cache_write_1h_price_per_million`.
- Create omits blank cache prices. The price editor sends only keys that differ from the prefill: a cache value sets it, and blanking a previously set cache price sends `null` to clear it. The input/output pair rule does not apply to cache prices. Input and output are sent, together, only when either one changed, because any input/output key makes Lumen flip the model to `manual`, clear its models.dev metadata and block later models.dev imports. An edit with no changes closes without a request.
- A stored zero that Lumen serializes in scientific form (`0E-10`) is shown and prefilled as `0`, so it no longer blocks later saves.
- Cache prices are checked in the form with a strict non-negative decimal pattern, and errors show in `Field`'s error slot. The trimmed string is sent unchanged, and Lumen still owns the precision limit.
- The model list shows any cache prices that are set. Otherwise it shows a neutral note that cache tokens bill at 0 USD until a cache price is set. The models.dev import copy still says catalog cache prices are not applied, and it points administrators to the price editor.
- The `usage.updated` parser (`chatContracts.ts`) accepts `cache_read_input_tokens`, `cache_creation_5m_input_tokens`, `cache_creation_1h_input_tokens` and the `advisor_cache_read_tokens` / `advisor_cache_creation_5m_tokens` / `advisor_cache_creation_1h_tokens` kinds, and still rejects unknown kinds.
- A model row without the cache keys (a Lumen that predates cache pricing) shows cache pricing as unsupported instead of a 0 USD note, and the editor hides its cache inputs; the create form hides them when every loaded row is such a row.
- Afterglow's `/api/v1/chat/{path}` BFF already forwards request and response bytes unchanged, which a new contract test now pins for the admin model routes.

## Capabilities

### Modified Capabilities

- Admin chat model pricing: per-model prompt-cache price entry, editing, and display.

## Impact

Affects `frontend/src/lib/components/admin/chat/ChatConfiguration.svelte`, `frontend/src/lib/api/chatContracts.ts` (and its test), the admin chat vitest suites, `backend/tests/contracts/test_lumen_proxy.py` (test only, no backend runtime change), `docs/api/chat.md` and `ARCHITECTURE.md`. No new colour, token, primitive, route, or backend endpoint. Lumen owns storage, validation, and billing. The rollout order is Afterglow first, then Lumen: the new Lumen emits cache and advisor-cache `usage.updated` kinds that the previous frontend's strict parser rejects, while this frontend also works against the previous Lumen once at least one model is loaded (with an empty model list the create form keeps its cache inputs, and a filled cache price on the first model is rejected by the previous Lumen with 422).
