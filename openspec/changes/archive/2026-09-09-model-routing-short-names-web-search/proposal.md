# Model Routing Short Names and Automatic Web Search

## Goal
Shorten model names in the administrator page so repetitive provider prefixes (such as `perplexity/perplexity/`) are stripped. Allow models without conflicting common denominators across providers to route successfully without requiring an explicit `provider` parameter. Automatically enable web search capabilities when models support web search.

## Scope
- **Frontend**: In `ChatConfiguration.svelte`, format model display names and API IDs cleanly by stripping redundant provider prefixes, and display web search capability badges in `ModelCapabilityBadges.svelte`.
- **Backend (Lumen)**:
  - Normalize model projection in `api_model_name()` and `display_name` to remove redundant duplicate provider prefixes (`perplexity/perplexity/...` -> `...`).
  - Update `resolve_api_model()` so that candidate matching checks both stripped and prefixed forms and automatically resolves models with no conflicting providers even when `provider` is omitted.
  - Detect `web_search` capabilities for Perplexity models and models declaring web search support.
  - In `_perplexity_completion()`, automatically include `{"type": "web_search"}` in Agent mode tool invocations when supported so the model can invoke real-time search when needed.
  - In `chat_admission.py`, allow models with native web search to default `provider_id` to their own provider when web search is requested or enabled.
