# Modernize array copies, request deadline and error cause

## Why

`modern-web-guidance legacy-scan` over the repository reported 63 findings. Most were `[...x].sort()` copies; the rest were a manual `AbortController` timer, a re-thrown error without its cause, four hand-written externalized promises, one `reduce` grouping and a handful of design-reference pages. Each finding was checked against its guide rubric before editing.

## What Changes

1. `[...x].sort(...)`, `x.slice().sort(...)` and `[...x].reverse().find(...)` become `x.toSorted(...)` and `x.findLast(...)` in 30 frontend files, only where the receiver is a declared array. Iterators (`map.keys()`, `.entries()`, `.values()`), `Set`/`Map` receivers and untyped receivers keep the spread.
2. `scripts/latency/api-lane.mjs` uses `AbortSignal.timeout(timeoutMs)` instead of an `AbortController` plus `setTimeout`/`clearTimeout`. `classifyFetchError` already maps both `AbortError` and `TimeoutError` to `deadline`.
3. `scripts/service-verify-http.mjs` `withCleanup` passes `{ cause: error }` when the cleanup failure is re-thrown; the message text is unchanged.
4. The frontend runtime image moves from `node:20-alpine` to `node:22-alpine` (`Dockerfile`), and the tag-push `setup-node` step in `docker-build.yml` from 20 to 22. This allows `Promise.withResolvers()` in four hand-written externalized promises (`coalescedRefresh.ts`, `WaygateProjectWorkspace.svelte`, `auth/callback/+page.svelte`, `dashboard/+page.svelte`) and `Map.groupBy()` in `AdminResourcePoliciesPanel.svelte` (`groupedPolicies()` runs during SSR render). The earlier attempt on Node 20 was reverted because neither API exists there (checked: `node:20-alpine` v20.20.2 reports `undefined` for both, `node:22-alpine` v22.23.5 reports `function`). Node 20 reached end of life in April 2026. Feasibility checked first: no production dependency requires Node 21+ or caps below 22, the Bun builder stage is unaffected, and CI vitest and the `native-node` stage already use Node 22.

## Not Changed, With Reasons

- `modelPricing.pricingPayload` keeps `JSON.parse(JSON.stringify(...))`: the guide forbids `structuredClone` when the result must be JSON-normalized or the source may be a reactive proxy.
- `[...catalogs.namespaces].sort()` and `[...messageArguments(nodes)].sort()` receive a `Set`; `toSorted` does not exist there.
- `layout.css` `:nth-child` stagger (`sibling-index()` is not Baseline widely available, so the rules would stay as the fallback), `ChatInput` auto-grow (`field-sizing` is not supported by Firefox, so the script stays), `chatRichOutput` `innerHTML` (already `DOMPurify.sanitize`d), and the static design-reference pages under `output/`, `frontend/static/theme/` and `scripts/character-assets/` (not product UI).

## Impact

No behavior, API or schema change. Deployment: the runtime image base changes, so the next release build ships Node 22; production keeps running the current Node 20 image until that release is rolled out. Browser baseline for the touched APIs: `toSorted`/`findLast`/`AbortSignal.timeout`/`Promise.withResolvers`/`Map.groupBy` are widely available in current browsers.
