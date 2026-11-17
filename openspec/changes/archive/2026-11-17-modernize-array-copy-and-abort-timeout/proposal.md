# Modernize array copies, request deadline and error cause

## Why

`modern-web-guidance legacy-scan` over the repository reported 63 findings. Most were `[...x].sort()` copies; the rest were a manual `AbortController` timer, a re-thrown error without its cause, four hand-written externalized promises, one `reduce` grouping and a handful of design-reference pages. Each finding was checked against its guide rubric before editing.

## What Changes

1. `[...x].sort(...)`, `x.slice().sort(...)` and `[...x].reverse().find(...)` become `x.toSorted(...)` and `x.findLast(...)` in 30 frontend files, only where the receiver is a declared array. Iterators (`map.keys()`, `.entries()`, `.values()`), `Set`/`Map` receivers and untyped receivers keep the spread.
2. `scripts/latency/api-lane.mjs` uses `AbortSignal.timeout(timeoutMs)` instead of an `AbortController` plus `setTimeout`/`clearTimeout`. `classifyFetchError` already maps both `AbortError` and `TimeoutError` to `deadline`.
3. `scripts/service-verify-http.mjs` `withCleanup` passes `{ cause: error }` when the cleanup failure is re-thrown; the message text is unchanged.

## Not Changed, With Reasons

- `Promise.withResolvers()` (4 sites) and `Map.groupBy()` (1 site) were applied and then reverted: the production frontend image is `node:20-alpine` (`Dockerfile`), SvelteKit SSR is enabled, and Node 20 has neither API (`Promise.withResolvers` needs Node 22, `Map.groupBy` Node 21). `groupedPolicies()` runs during render, so a server `TypeError` would return 500. Revisit together with a frontend image move to Node 22 or later (Node 20 reached end of life in April 2026); that is a deployment change and was not made here.
- `modelPricing.pricingPayload` keeps `JSON.parse(JSON.stringify(...))`: the guide forbids `structuredClone` when the result must be JSON-normalized or the source may be a reactive proxy.
- `[...catalogs.namespaces].sort()` and `[...messageArguments(nodes)].sort()` receive a `Set`; `toSorted` does not exist there.
- `layout.css` `:nth-child` stagger (`sibling-index()` is not Baseline widely available, so the rules would stay as the fallback), `ChatInput` auto-grow (`field-sizing` is not supported by Firefox, so the script stays), `chatRichOutput` `innerHTML` (already `DOMPurify.sanitize`d), and the static design-reference pages under `output/`, `frontend/static/theme/` and `scripts/character-assets/` (not product UI).

## Impact

No behavior, API, schema or deployment change. Browser baseline for the touched APIs: `toSorted`/`findLast`/`AbortSignal.timeout` are widely available; Node 20 supports all three.
