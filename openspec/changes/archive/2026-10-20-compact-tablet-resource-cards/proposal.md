## Why
Tablet/mobile table views require horizontal scrolling and waste space on secondary fields. User requests all table views become compact cards at tablet-and-below widths, preserving meaningful information and operations.

## What Changes
Audit all native table and div-grid table views in user/admin routes, detailed panels/modals and embedded data disclosures. Add shared viewport-responsive ResponsiveTable and CompactResourceCard primitives; author domain-specific compact summaries. Below1024px VIEWPORT render cards only; desktop remains table even inside a narrower panel/sidebar layout. Prioritize name/status and2–3key values, retain other values in details or existing detail surface. Selection, actions, sorting, filtering, paging, failures and authority remain intact. No API/schema/config/dependencies/deploy changes.

## Acceptance
Every inventoried application table has a compact card path, not merely overflow hiding or table cells stacked into giant rows.1040/1024/1023/768/767/390/320 widths and narrow desktop panels exercised with long labels/identifiers, selection/actions/paging and locale/theme. Relevant existing tests and actual compiled/source browser evidence, docs and architecture review, OpenSpec archive. Preserve unrelated WIP and no production rollout.
