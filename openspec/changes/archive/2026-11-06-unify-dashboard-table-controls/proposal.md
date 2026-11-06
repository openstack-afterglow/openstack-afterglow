## Why

Dashboard tutorials, search, sorting and filters differ between resource pages. Users report missing image guidance, misplaced tutorial actions and refresh losing active query conditions; table filtering must become a consistent column-oriented interaction.

## What Changes

- Audit every application-owned table and dashboard route, including administrator and compact views.
- Put existing tutorial entry points beside top-level create/edit actions and add the image inventory tutorial.
- Use always-on case-insensitive regular expressions for resource/table search, with explicit invalid-pattern feedback.
- Preserve query, column filters and ordering through manual/background refresh and ordinary same-owner credential renewal; retain privacy resets for actual owner/scope changes.
- Replace list toolbar exact-value filters and sort selectors with accessible column sort controls and adjacent searchable value-filter popovers. Apply typed data projections before pagination and selection, with equivalent compact controls.
- Preserve native server-pagination boundaries and explicitly label loaded-page filtering rather than inventing whole-inventory results.

## Capabilities

### New Capabilities
- `dashboard-table-controls`: Consistent tutorial placement, regex search, durable refresh view state and accessible column sort/value filters across application-owned inventories and tables.

### Modified Capabilities
None.

## Impact

Frontend shared UI/query utilities, tutorial registry, table-bearing route/components, all supported locale catalogs, relevant behavioral tests and design/architecture/user/testing documentation. No native cloud write, backend endpoint, database migration, new dependency, release or production deployment is requested. Shared checkout changes and index remain preserved.
