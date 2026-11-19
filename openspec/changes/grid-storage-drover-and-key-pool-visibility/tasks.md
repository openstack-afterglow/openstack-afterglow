## 1. Implementation

- [x] Dashboard trend cards: remove chart-data and telemetry-collection disclosures; tests updated.
- [x] Instance grid: per-port security-group chips, selected-group expansion, volumes and file shares; controller reads storage attachments.
- [x] Drover cluster grid with bounded per-node reads and honest unknown states.
- [x] Provider key pool identity labels, registration date, monthly usage and totals; nine locales.

## 2. Verification

- [x] Focused vitest suites, i18n check, svelte-check on touched files; synthetic browser proof of instance and Drover grids.
- [ ] Isolated `npm run test:gate`.
- [ ] Production verification after release and rollout (instance with ports/volumes/shares, Drover cluster, provider key pool against Lumen with the new fields).
