## 1. Implementation

- [x] Dashboard trend cards: remove chart-data and telemetry-collection disclosures; tests updated.
- [x] Instance grid: per-port security-group chips, selected-group expansion, volumes and file shares; controller reads storage attachments.
- [x] Drover cluster grid with bounded per-node reads and honest unknown states.
- [x] Provider key pool identity labels, registration date, monthly usage and totals; nine locales.

## 2. Verification

- [x] Focused vitest suites, i18n check, svelte-check on touched files; synthetic browser proof of instance and Drover grids.
- [x] Isolated `npm run test:gate` on 48b91dae: backend 15,702 passed / 107 skipped, frontend 8,782 passed, contracts 329, functional 301 passed / 46 skipped, Ruff clean.

## 3. Admin and usage follow-ups (PR #118, a64c43cc)

- [x] `/dashboard/usage` trend cards and per-instance rows: remove telemetry source, native-state and native-policy lines; keep empty/partial/failed status text. VM monitoring and admin charts deliberately keep the chart-data table.
- [x] API key pool: every account/key setting (priority, weight, quota group, allowed model IDs and operations, expiry, cooldown end, generation, current endpoint, key state) as a labelled entry with an explanation; accounts and keys sorted by priority then ID; `선택 순서 N` only under the priority policy; aligned month/all-time summary per key.
- [x] Model settings: tabs per model kind (only kinds with models, counts), provider-grouped lists in `sort_order`/ID order, last tab remembered, provider filter and select-all scoped to the visible tab, reorder payload built from the provider's full list.
- [x] Isolated `npm run test:gate` on a64c43cc: backend 15,702 passed / 107 skipped, frontend 8,789 passed, contracts 329, functional 301 passed / 46 skipped, Ruff clean; browser proof on mockup data (desktop and 390 px).

## 4. Production

- [ ] Production verification after release and rollout (instance with ports/volumes/shares, Drover cluster, provider key pool with the new setting explanations, priority order and month/all-time usage against Lumen with `created_at`/`month_*` fields, model settings kind tabs including an audio/realtime tab with real models, `/dashboard/usage` without telemetry source lines).
