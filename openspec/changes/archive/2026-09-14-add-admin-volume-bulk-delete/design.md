## Context

`/admin/volumes` already paginates Cinder volumes across projects and has safe single-volume deletion, but its table has no selection state. The repository already provides `SelectionCheckbox`, `BulkSelectionOverlay`, `createResourceSelection`, confirmation, and toast primitives. The status-summary API returns only statuses present in Cinder, while the frontend currently expands that data into nine cards and options including zero-count states.

The list response does not include attachments, so the browser cannot reliably determine deletion eligibility. Cinder remains authoritative and the admin API must report failures per requested volume rather than guessing from list status.

## Goals / Non-Goals

**Goals:**
- Select individual rows or every row on the currently loaded page at desktop and touch widths.
- Confirm destructive bulk deletion and preserve failed selections for retry or inspection.
- Execute up to 50 unique volume deletions through one admin API while isolating per-volume failures.
- Hide status filters whose current cluster-wide count is zero and reset an active status filter if that state disappears.
- Clear selection at page/filter/page-size/project-scope boundaries.

**Non-Goals:**
- Select resources across unloaded marker pages.
- Force-delete attached volumes or bypass the existing single-delete safety behavior.
- Add database state, background jobs, retries, or a new visual primitive.
- Change Cinder ownership, admin authorization, or cache boundaries.

## Decisions

- Reuse `createResourceSelection`, `SelectionCheckbox`, and `BulkSelectionOverlay`. This follows the design-system resource-selection contract and avoids route-specific checkbox or fixed-action-bar behavior.
- Treat every loaded row as selectable because the compact admin list does not expose authoritative attachment data. The server attempts each deletion using the same helper as the single DELETE endpoint; Cinder rejections become per-item failures and remain selected.
- Add `POST /api/v1/admin/volumes/bulk-delete` with `volume_ids`. The request rejects empty, duplicate, or more than 50 IDs. Sequential per-item execution limits Cinder pressure, continues after failures, and returns `{results: [{id, ok, error?}]}` in request order.
- Extract the current single-delete implementation into a shared synchronous helper used by both routes. This prevents semantic drift between single and bulk deletion.
- Drive both summary cards and the status `<select>` from positive counts in `status-summary`. The total card always remains. If a selected state disappears, reset to the total filter and reload the first page so no hidden active filter remains.
- Snapshot token and project scope before mutation. Publish results and refresh selection/list/summary only if the scope still matches, preventing stale mutation completion from altering a newly selected admin context.

## Risks / Trade-offs

- [Risk] A listed volume can become attached after selection. → Let Cinder reject that item; keep it selected and report a failure without blocking other deletions.
- [Risk] Deleting all rows on a marker page can leave an empty current page. → Refresh the current marker and retain normal pagination; the operator can navigate backward without inventing cross-page selection state.
- [Risk] Status summary refresh can race with another filter change. → Apply automatic reset only when the completed summary still corresponds to the current auth scope and active filter.
- [Trade-off] Sequential deletion is slower than unconstrained parallel calls. → The 50-item cap and predictable Cinder load are safer for an operator-triggered destructive action.