## Implementation Tasks

- [x] Inspect and reproduce the current role list/authorization and role exposure behavior; define the API and security contract.
- [x] Implement system-admin-only role CRUD, real direct/transitive inference data, safe deletion, and lower-role edge add/remove with cycle and elevation validation.
- [x] Prevent ordinary users from seeing/selecting privileged role identities or using role management endpoints, while preserving internal effective authorization and project ownership.
- [x] Implement searchable sortable list/tree views, role create/edit/delete, and selectable direct lower-role controls with transitive-role context.
- [x] Exercise authorization/graph regressions and the actual role dashboard in Chromium, including responsive layouts, errors, and ordinary-user denial.
- [x] Update API/design/architecture/changelog documentation with truthful verification limits and archive the completed change.
