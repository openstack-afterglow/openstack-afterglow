## Why

`/admin/services` showed every Nova/Cinder/Neutron/Manila/Heat/Zun/Magnum row, API endpoint, and storage pool in response order only. Operators could not isolate `down` services on one host, compare `Status` and `State` independently, or sort hosts and capacities, so the page did not help during incident triage.

## What Changes

- Add per-tab search, combinable filters, and column sorting to all nine service tabs.
- Treat `Status`/`State` and Network `Alive`/`Admin State` as independent AND conditions; keep unknown values distinct from `down`.
- Sort text naturally (`host2` before `host10`), capacities numerically, and `Updated` by UTC timestamp; missing values stay last in both directions.
- Preserve each tab's search/filter/sort across tab switches and manual/auto refresh, keep existing rows interactive during background refresh, and distinguish zero source rows from zero matching rows with a reset action.
- Keep the existing lazy category loading, hover prefetch, selected-tab refresh, backend API, permissions, and cache contracts unchanged.

## Capabilities

### New Capabilities
- Admin service list filtering, search, and sorting within loaded category data.

### Modified Capabilities
- Admin services page state handling (per-tab view state, refresh preservation) and list presentation using shared Field/input/Button/TableShell primitives.

## Impact

- Frontend only: `frontend/src/lib/components/admin/services/*`, `frontend/src/lib/types/adminServices.ts`, `frontend/src/routes/admin/services/+page.svelte`, related tests, `legacyVisualDebt.ts` baseline entries for rewritten service components.
- Documentation: `ARCHITECTURE.md`, `docs/api/admin.md`, `CHANGELOG.md`.
- No backend endpoint, schema, dependency, deployment, or OpenStack call changes.
