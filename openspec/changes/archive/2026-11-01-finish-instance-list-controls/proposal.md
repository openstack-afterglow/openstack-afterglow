## Why

The project instance list spends desktop width on unnecessary horizontal scrolling and separates related controls. Column sorting should be direct without losing the same capability in compact cards.

## What Changes

- Fit the fixed desktop table to adequately wide content shells, reserving the actual action-trigger width and wrapping long IP/library values.
- Replace the project instance sort select with six sortable columns and equivalent accessible compact buttons.
- Keep newest-first default, cycle ascending/descending/default, and reset pagination and selection on sort changes.
- Group page size with previous/next and place the VM tutorial beside creation.
- Localize controls in all nine supported locales and preserve permissions, data and mutation fences.

## Capabilities

### New Capabilities
- `project-instance-list-controls`: Responsive instance table sizing, column sorting and related control placement.

### Modified Capabilities
None.

## Impact
Project instance Svelte page/list components, pure display sorting, locale catalogs, tests and UI documentation. No API, database, native cloud, dependency or deployment changes.
