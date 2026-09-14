## 1. Backend bulk deletion

- [x] 1.1 Extract shared admin volume deletion logic and add validated bulk-delete request/result handling
- [x] 1.2 Add backend regressions for authorization, validation, request order, and partial failure

## 2. Admin volume selection UI

- [x] 2.1 Add page-scoped selection state, confirmation, bulk result feedback, and safe boundary resets
- [x] 2.2 Add shared selection checkboxes and bulk overlay to the admin volume table/page
- [x] 2.3 Add component/page regressions for select-all, partial success, and failed-selection retention

## 3. Status filter visibility

- [x] 3.1 Render only positive-count status cards and status-select options
- [x] 3.2 Reset a hidden active status filter and add focused regressions

## 4. Documentation and verification

- [x] 4.1 Update DESIGN.md, ARCHITECTURE.md, docs/api/admin.md, and CHANGELOG.md
- [x] 4.2 Run focused backend/frontend checks and browser verification across required responsive cutovers
- [x] 4.3 Stamp and validate the architecture review, then archive the OpenSpec change