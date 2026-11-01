## Implementation Tasks

- [x] Inspect reported screenshots, current HUD placement, card address geometry and existing topology collision/zoom contracts.
- [x] Replace previous-zone pushing with measured screen-space HUD placement against all cards, headings, labels and visible badges; preserve anchored selection and readable name/CIDR content.
- [x] Add deterministic geometry and actual-component regressions, including overlapping zones, zoom/drag, narrow widths and long addresses; expose stable synthetic browser fixture paths (`__tests__/TopologyLabelHarness.svelte`, `makeLabelCollisionFixture`, `LABEL_COLLISION_POSITIONS`).
- [x] Update relevant ARCHITECTURE, DESIGN and CHANGELOG entries without touching docs/testing, review stamps or archived changes.
- [x] Parent: final16files279tests and Svelte0errors17warnings; actual compiled component both themes/390·768·1440px/normal+long IPv6 labels, five live zoom actions and stable fitted narrow bounds verified. Evidence and unexercised boundaries recorded in docs/testing.md.

Exact parent selectors: `npm run test:target -- frontend:src/lib/components/topology/canvas/__tests__/hudLayout.test.ts`, `frontend:src/lib/components/topology/canvas/__tests__/CanvasHud.test.ts`, and `frontend:src/lib/components/topology/canvas/__tests__/TopologyCanvas.test.ts`. Also retain existing topology layout/graph regressions for integration. New worker changes have not been tested or built; browser mounting and measured DOM acceptance belong to the parent.

Browser proof used temporary actual-component harness with synthetic fixture and no API callbacks; removed after acceptance. Recorded conditions, including offscreen/transition limitations, are in docs/testing.md and ~/.local/share/afterglow-proofs/topology-labels-20261101/. No cloud/deployment acceptance is claimed.
