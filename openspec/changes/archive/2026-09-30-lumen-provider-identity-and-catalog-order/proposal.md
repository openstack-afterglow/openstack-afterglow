## Why

The Lumen administrator cannot rename providers or edit the public API selector separately from the endpoint transport. Every OpenAI-compatible endpoint currently advertises `provider=openai`, including NVIDIA NIM. Registered models have no provider filter, and the user model picker's provider navigation and model groups do not have a persisted administrator-controlled order.

## What Changes

- Edit provider display `name` independently from a persisted `api_provider` selector and existing `provider_type` transport. For example, the existing NVIDIA NIM row can be renamed NVIDIA with `api_provider=nvidia`, while preserving `provider_type=openai`, provider ID, models, credentials and base URL.
- Add an additive Lumen migration that backfills existing selectors from `provider_type`, without silently renaming existing providers or API clients. Existing migration SQL/checksums are immutable.
- Use the stored selector in model projections and compatibility request resolution; retain actual transport type for capability, billing, credential, price, discovery and execution decisions. Distinct selectors sharing a public model ID require disambiguation; display order must never choose an inference route.
- Add persisted nonnegative integer `sort_order` to providers and models. Lower values display first; provider/model IDs are deterministic tie-breakers. Apply provider order consistently to picker navigation and group headers, and model order within each group. Ordering changes do not rename model IDs, alter pricing/capabilities or select a different configured model.
- Add a separate provider filter to the registered-model administration list. Discovery/creation selection is independent. Bulk selection and deletion operate only on visible filtered models; hidden selection must not leak across filters.
- Compose existing form/modal/button primitives; keep edit/filter/order actions accessible at mobile, tablet and desktop sizes. Successful mutations invalidate the existing model catalog signal.

## Capabilities

### New Capabilities

- Provider presentation and API-selector editing.
- Registered-model provider filtering.
- Administrator-controlled provider and model presentation order.

### Modified Capabilities

- Lumen model catalog projections and external provider-qualified resolution.

## Impact

Persistence, migration and request resolution remain Lumen-owned. Afterglow forwards authenticated public requests and renders the administrator/user surfaces; it does not import Lumen modules or access Lumen's DB. Afterglow stays on dev. Lumen backend work uses `/Users/pieroot/code/lumen-provider-identity` on `feature/provider-identity-catalog-order`, based on the current 0.4.0 release commit, preserving the original release checkout's unrelated dirty work. No commit, push or deployment is authorized. Focused consumer-visible regressions, real isolated datastore migration/persistence and HTTP/browser smoke will distinguish local evidence from live provider/production acceptance.
