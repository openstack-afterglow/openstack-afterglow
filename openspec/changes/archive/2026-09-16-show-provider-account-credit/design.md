## Context

The administrator provider cards already consume one bulk Lumen billing snapshot. That response contains Lumen-attributed usage for every provider, official OpenAI/Anthropic organization usage, OpenRouter per-key limit data, DeepSeek account balances, and trusted billing/usage console URLs. The current rendering branches directly on provider capability: DeepSeek and OpenRouter expose their credit values, while OpenAI and Anthropic show only organization usage and give no explicit explanation that their official APIs do not expose current prepaid balance or purchased-credit totals.

Provider financial concepts are not interchangeable. OpenRouter's `limit_remaining` is a per-key spending limit, DeepSeek's `total_balance` is an account balance, and OpenAI/Anthropic cost reports are incurred usage rather than remaining credit. The UI must retain these distinctions.

## Goals / Non-Goals

**Goals:**
- Give every provider card an explicit, scannable account-credit state separate from usage.
- Present exact provider-returned balance, purchased, granted, limit, and remaining values with their real scope.
- State when the official provider API does not expose account credit and keep the official billing console reachable.
- Preserve responsive information parity and current billing failure isolation.

**Non-Goals:**
- Do not estimate balance as deposits minus usage.
- Do not scrape provider dashboards or accept browser session cookies.
- Do not add credentials, provider HTTP requests, database state, or BFF routes.
- Do not reinterpret rate-limit headers as monetary credit.

## Decisions

### Derive a typed credit view from the existing bulk snapshot

`ChatConfiguration.svelte` will map each `ProviderBilling` snapshot to a small discriminated credit view used only for rendering. DeepSeek maps to account-balance entries, OpenRouter maps to an API-key-limit view, an unavailable supported capability maps to a retryable lookup failure, and all other providers map to an explicit API-not-exposed view.

This keeps Lumen as the financial-data authority and avoids a second provider-name contract or per-provider network request. Adding a new Afterglow API response would duplicate fields already returned by Lumen.

Alternative considered: add `credit_status` to Lumen. Rejected for this change because no new source data is needed and the repo-local change cannot alter the sibling service contract safely.

### Keep credit and usage as separate semantic groups

The card will render `계정 크레딧` before the existing Lumen and official organization usage groups. DeepSeek values will be labeled as account balance, purchased credit, and granted credit. OpenRouter values will be labeled as the configured API key's limit and remaining limit, never as account balance. OpenAI, Anthropic, Gemini, and other providers will show `공식 API 조회 미지원` with concise provider-specific explanation.

Alternative considered: add one extra metric tile to the current official-usage grid. Rejected because a missing balance would look like a failed or zero usage metric and because OpenRouter's key scope differs from account scope.

### Place official billing action next to the credit state

The existing server-provided HTTPS billing URL remains the only external credit-management target. The shared `Button` primitive retains `target="_blank"`; it supplies opener-safe link behavior. No URL is synthesized in the browser.

### Preserve existing data-fetch and failure semantics

The page continues to make one bulk billing request. Billing failure remains independent from provider CRUD. A provider capability failure displays a retryable unavailable state; a provider that has no documented balance endpoint displays a non-error unsupported state.

## Risks / Trade-offs

- [Administrators may read OpenRouter key remaining limit as account balance] → Label the scope as `API 키 한도` and state that it is not the account-wide prepaid balance.
- [A provider adds a balance API later] → Keep the unsupported state explicit and update Lumen capability data before enabling a numeric display.
- [More information increases card height] → Use compact semantic groups and the existing two-column mobile/four-column desktop grids; do not hide information at narrow widths.
- [Provider portal URLs change] → Continue accepting only Lumen-owned HTTPS URLs so link maintenance stays server-side.

## Migration Plan

1. Ship the frontend rendering and focused tests against the existing backward-compatible bulk billing response.
2. No database or Lumen migration is required.
3. Rollback is the frontend commit only; the billing API and stored credentials are unchanged.

## Open Questions

None. Official API support is represented conservatively: only current documented Lumen balance fields produce numeric credit state.
