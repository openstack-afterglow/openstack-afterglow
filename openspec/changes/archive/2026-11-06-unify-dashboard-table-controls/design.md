## Context

Application tables use authored Svelte table/card snippets and typed arrays; TableShell only supplies presentation. Resource query state belongs to routes/controllers, with some server marker pagination. No DOM scraping, row reordering, cloned controls or MutationObserver enhancement is acceptable.

## Goals / Non-Goals

Goals: complete application-owned table inventory; consistent top-level tutorials; always-regex searches with errors; column sorting and searchable exact-value multi-filters before pagination; refresh state retention and compact parity.

Non-goals: cloud mutations, new server pagination contracts, server-side regex, external/user Markdown tables, credentials in view persistence, deployment or unrelated redesign.

## Decisions

- Add a typed createTableView rune utility and TableColumnControl presentation primitive. Data owners supply key/label/value accessors. Query/filter/sort are owner state, never DOM-derived. Local complete arrays filter/sort before slicing; server pages explicitly operate on loaded records without inventing totals.
- Columns cycle ascending, descending, default; unknown numeric/text values sort last in either direction and stable ties retain incoming default order. Exact value selections are OR within a column and AND across columns. Value menus include retained unavailable selections so refresh never silently clears a condition.
- Always compile case-insensitive Unicode regular expressions once per query change; invalid expressions match no rows and display localized feedback rather than reverting to literal or empty search.
- Keep refresh handlers read-only with respect to view state. Actual logical actor/scope changes retain existing privacy resets; normal bearer renewal must not remount/reset controls.
- Top-level tutorial actions compose PageHeader actions, not toolbar slots. Existing synthetic tutorial transport remains isolated from real cloud mutations.
- Reuse semantic tokens, portal placement and keyboard/outside dismissal patterns. Compact layouts expose the same column controls above authored cards, not scraped tables.

## Risks / Trade-offs

- Native JavaScript regular expressions have backtracking cost: compile once and do not add network requests per keystroke. Arbitrary regex remains user-controlled local matching.
- Native marker pages are not whole inventories: use loaded-page wording and preserve continuation.
- Many independently authored tables require explicit adapters; an inventory/coverage receipt prevents a primitive-only incomplete cutover.
- Shared checkout contains unrelated edits: preserve them and centralize documentation/catalog integration.
