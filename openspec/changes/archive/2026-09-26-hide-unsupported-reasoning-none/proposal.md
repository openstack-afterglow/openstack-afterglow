## Why

The chat effort picker always offered `none` ("없음") for every reasoning model. Lumen now rejects an explicit `reasoning_effort="none"` with 422 unless the model can disable reasoning. LiteLLM 1.93 forwards `none` unchanged to OpenAI gpt-5 and o3, which reject it, and maps it to an invalid `thinkingBudget: 0` for gemini-2.5-pro. Without a client change, users of those models get a failed send.

## What Changes

- `effortOptionsFor` and `normalizeEffort` offer `none` only when Lumen `GET /v1/chat/models` reports `reasoning_none_supported: true` for the selected model. The client does not copy Lumen's rule (effort list with `none`, `toggle`, `budget_tokens` minimum 0, or an Anthropic provider).
- A missing field (older Lumen) hides `none` and normalizes the current `none` selection to `auto`, which fails safe.
- Regenerating with a per-message model normalizes the effort against the model that actually runs (`effortForModel`), so a `none` chosen for gpt-5.1 is not sent to gpt-5.
- `AvailableModel` gains the optional `reasoning_none_supported` field; `ChatPanel` passes it to `ChatInput`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- Chat effort selection hides the explicit reasoning-off choice for models whose Lumen admission would reject it.

## Impact

Frontend only; the BFF forwards `/api/v1/chat/models` unchanged. The companion Lumen change adds `reasoning_none_supported` and the 422. Before Lumen is upgraded the choice is hidden for all models, which only removes an option. Rollout order: deploy this Afterglow change before or together with the Lumen 422; the reverse order leaves the old UI offering "없음" on gpt-5/o3, and those sends fail.
