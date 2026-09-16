## Why

Lumen currently exposes LiteLLM transport-prefixed Perplexity model names such as `perplexity/perplexity/sonar` as public API IDs and resolves compatibility requests by internal model name alone. This leaks transport encoding into Afterglow, makes duplicate-looking model IDs visible, and cannot deterministically select a Perplexity route when the same canonical GPT or Claude model is also configured directly.

## What Changes

- Separate the stable internal model route key from deterministic public `api_model_name` and transport `api_provider` metadata.
- Canonicalize Perplexity discovery and new registrations while preserving existing rows, durable snapshots, history, pricing provenance, and native model selection keys.
- Route Perplexity Agent, Router, and legacy Sonar requests through explicit product-specific LiteLLM paths without credential fallback or retrying another mode.
- Add provider-aware, ambiguity-safe model resolution to the OpenAI and Anthropic compatibility APIs and return canonical model IDs in responses and model listings.
- Update Afterglow administration, model picker, clipboard actions, and SDK examples to use the public model/provider contract while retaining internal keys for native selection.

## Capabilities

### New Capabilities

- Deterministic public model identity independent of LiteLLM transport encoding.
- Explicit `provider` selection on OpenAI and Anthropic compatibility requests.
- Perplexity Agent and Router transport routing with canonical upstream model IDs.
- Provider-aware model listing and copyable `{model, provider}` request configuration.

### Modified Capabilities

- Perplexity discovery, model creation/update validation, and duplicate detection.
- Lumen model/catalog response schemas and compatibility response projection.
- Afterglow chat administration, model picker search/display, and SDK connection examples.

## Impact

Lumen provider, routing, discovery, compatibility API, and transport services change together with focused contract tests and provider documentation. Afterglow consumes the added metadata in existing chat UI components and documentation. No database migration, model alias table, historical rewrite, new endpoint, provider credential source, or deployment change is introduced. Existing internal `model_name` values remain the native route and durable provenance key.
