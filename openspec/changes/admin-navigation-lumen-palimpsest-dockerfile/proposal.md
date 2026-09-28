## Why

Admin service links are split across unrelated groups; Waygate's administrator link currently lands on the tenant view. Lumen's composer uses unreadable light-mode overlays. Palimpsest exposes multiple partially overlapping build workflows whose Dockerfile FROM, cache, boot, seal, and consumer contracts do not consistently produce or consume a complete filesystem.

## What Changes

- Add a distinct admin `서비스` group for Drover, Lumen, Palimpsest, and Waygate, backed by administrator routes; retain tenant Waygate within tenant Network. Align command palette and tutorial routes and enforce current project scope on tenant Waygate.
- Repair the Lumen composer in light mode using the existing design tokens across idle, focus, disabled, toolbar, placeholder, and attached content states without altering dark tokens.
- Make a Dockerfile with an explicit `FROM` the only new-build authoring surface. Support inline and safe URL/file text inputs; keep GitHub pinned imports only if routed through the same job planner, executor, cache, and build record. Remove obsolete create controls, not the historic layer and import records.
- Resolve supported Ubuntu Glance images and sealed Palimpsest parents unambiguously; materialize the full boot image filesystem for Glance roots and preserve a full root across inherited steps; cache only sealed, matching parent+step prefixes. The builder runs steps, seals digested artifacts, persists source/base/parent/cache lineage and terminal status, and cleans owned resources on failure.
- Boot consumers with a lower root covering the full filesystem and ordered read-only ancestor deltas, retain a writable upper, expose an actual guest-ready signal, and preserve legacy unlayered, GPU, and data-mount creation. Route both administrator and public endpoints to the same execution state machine while retaining ownership and access restrictions.
- Verify failing-before/after regressions, named and full gates, UI/light-mode browser flows, Linux guest build/consume checks, and available live OpenStack/SSH/cleanup checks. Update architecture, API, design, changelog, and the test stamp guard only for fully observed results.

## Capabilities

### New Capabilities

- Dockerfile-rooted Palimpsest build and complete-root consumption with explicit base-image and cache provenance.
- Distinct administrator service navigation and administrator Waygate workspace.

### Modified Capabilities

- Lumen light-mode composer contrast and responsive usability.
- Palimpsest build job, cache, builder, API, history and consumer lifecycle; Waygate tenant scope and tutorial/command routing.

## Impact

SvelteKit admin/user routes and shared navigation, FastAPI Palimpsest and VM adapters, persisted build metadata/migrations, cloud-init/Linux scripts, tests, architecture and API docs. Preserve existing user work and legacy layer records; no production rollout or destructive migration is implied. Live OpenStack proof is required before claiming deployment readiness.
