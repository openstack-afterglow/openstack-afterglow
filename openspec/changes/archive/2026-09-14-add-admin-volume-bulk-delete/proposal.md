## Why

The admin all-volumes page only supports one-at-a-time deletion and renders status filters that cannot match any volume. Operators need a safe page-scoped bulk delete flow and a status summary that exposes only actionable filters.

## What Changes

- Add page-scoped select-all and per-row selection to the admin all-volumes table using the shared resource-selection primitives.
- Add a confirmation-gated bulk delete action that reports per-volume successes and failures, preserves failed selections, and refreshes the current page plus status summary.
- Add an admin bulk volume delete API accepting at most 50 unique volume IDs and returning one result per requested volume without stopping after an individual failure.
- Hide zero-count status cards and zero-count status options after the status summary loads while retaining the total filter.
- Clear page-scoped selection when filters, page size, pagination, or admin project scope changes.

## Capabilities

### New Capabilities
- `admin-volume-bulk-management`: Page-scoped volume selection, partial-success bulk deletion, and data-driven status filter visibility on the admin all-volumes surface.

### Modified Capabilities
- None.

## Impact

- Backend: `backend/app/api/identity/admin.py` and focused admin volume tests.
- Frontend: `frontend/src/routes/admin/volumes/+page.svelte`, admin volume table/filter/summary components, and focused component/page tests.
- Documentation: `ARCHITECTURE.md`, `DESIGN.md`, `docs/api/admin.md`, and `CHANGELOG.md`.
- No database schema, dependency, deployment, or OpenStack ownership-boundary changes.