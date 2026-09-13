## Why

Compact chat layouts place their sidebar reopen control beneath the application header, making history and user settings unreachable. Settings lacks a visible chat return path. Search capability detection is limited to Perplexity, source lists appear after answers, and Perplexity completion/context admission rejects text with pricing_unavailable.

## What Changes

- Keep chat navigation reachable at mobile/tablet widths using the existing drawer and header composition; preserve history and user menu actions and keyboard dismissal.
- Add an explicit return-to-chat action to the dedicated settings route.
- Expose Search using actual provider/API capability metadata, with an explicit native-search request option where the provider supports opt-in search. Do not claim subscription transport support.
- Render safe, ordered citation sources above their corresponding assistant answer, including live and restored messages.
- Correct Perplexity canonical-ID price resolution in Lumen without disabling fail-closed price admission or inventing unknown model prices.

## Capabilities

### New Capabilities

- Optional native API web search on supported chat models, distinct from managed search provider selection.

### Modified Capabilities

- Responsive chat navigation and settings return path.
- Provider capability/pricing projection and citation presentation.

## Impact

Afterglow owns chat UI and request contracts. The sibling Lumen checkout owns native provider requests, capability detection, price resolution and citation normalization. Preserve provider selection separate from public model IDs, pricing/quota security, durable SSE and existing managed search contracts. Validate focused regressions, responsive browser interaction and full repository gates; do not deploy.
