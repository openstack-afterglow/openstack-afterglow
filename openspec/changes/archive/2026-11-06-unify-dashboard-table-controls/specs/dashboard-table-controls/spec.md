## ADDED Requirements

### Requirement: Top-level tutorial placement
Every existing page tutorial SHALL appear in the highest page action area beside create/edit actions, or beside the title when no mutation action exists. Image inventory SHALL expose a working tutorial.

#### Scenario: Open image inventory
- **WHEN** a user opens the image inventory and activates its top tutorial action
- **THEN** the authored image tour runs through its supported synthetic transport without a real resource mutation

### Requirement: Always regular-expression search
Every application resource/table and form-option search SHALL apply a case-insensitive regular expression and expose invalid syntax without literal fallback or silently disabling the condition.

#### Scenario: Regex and invalid syntax
- **WHEN** a user enters an anchored alternation pattern and then an invalid bracket
- **THEN** matching rows follow regex semantics and invalid syntax produces visible feedback without exposing unrelated rows

#### Scenario: Search a form-option picker
- **WHEN** an anchored label/description expression or invalid pattern is entered in a resource picker
- **THEN** fields match independently, invalid syntax exposes no selectable option, and correcting the expression restores valid selection

### Requirement: Refresh preserves view state
Manual and automatic refresh SHALL retain search, column filters and sorting for the same logical owner/scope. Existing privacy clearing on actual scope/authority change SHALL remain.

#### Scenario: Force refresh with active conditions
- **WHEN** a user refreshes an inventory with an active regex, exact-value column selection and descending sort
- **THEN** new rows are projected through the unchanged conditions and ordering

### Requirement: Column-oriented controls
Application-owned data tables SHALL provide keyboard-operable ascending/descending/default header sorting and adjacent searchable value filtering. Toolbar field filters/order selectors SHALL migrate to those controls. Compact layouts SHALL expose equivalent controls over the same typed data.

#### Scenario: Announce an active column condition
- **WHEN** a column has an active value or range condition
- **THEN** assistive technology receives the localized selected-condition count without changing the trigger name, including an active empty selection

#### Scenario: Combine column filters
- **WHEN** a user selects multiple values in one column and a value in another
- **THEN** values combine with OR within each column and AND across columns before local pagination and visible selection

#### Scenario: Refresh removes a selected value
- **WHEN** fresh inventory no longer contains a selected column value
- **THEN** the selection remains active and removable instead of silently widening the results

#### Scenario: Native marker pagination
- **WHEN** a table receives only a native marker page
- **THEN** local projection is labeled as loaded-page filtering and continuation remains reachable without claiming whole-inventory totals

### Requirement: Preserve server-wide query capabilities
Existing native column predicates and supported sort orders SHALL move to header options without being downgraded to current-page-only filters. Scalar native predicates SHALL use explicit single-value controls, arbitrary numeric bounds SHALL remain available in the quantity header, and arbitrary exact/contains provider values SHALL remain a clearly labeled column predicate rather than a second literal search box. Only unsupported columns SHALL use loaded-row local filtering.

#### Scenario: Find a status or user outside the first marker page
- **WHEN** an administrator applies an existing native status, host, user or action condition from its column menu
- **THEN** the original native query parameter and first-marker reload are used, preserving access to matches outside the currently loaded page

#### Scenario: Apply a header while form drafts are pending
- **WHEN** an event header predicate is applied before pending period/request/interaction fields are explicitly submitted
- **THEN** only that native predicate changes, list and statistics preserve the applied window, and refresh does not submit those drafts

#### Scenario: Provider accepts one facet value
- **WHEN** a native scalar column condition is selected
- **THEN** the UI permits exactly one value and never pretends that an unsupported OR query was applied

### Requirement: Complete coverage verification
Every table-bearing route/component SHALL be inventoried and checked, including empty/error states, compact presentation and retained native pagination. Verification SHALL distinguish local/synthetic browser evidence from production acceptance.

#### Scenario: Complete migration review
- **WHEN** the change is marked complete
- **THEN** its coverage receipt identifies every application-owned table, adapter and exercised verification with no silently omitted dashboard family
