## Why

The project member role editor labels existing inherited permissions read-only but leaves their checkboxes unchecked and selectable. The operator must scroll through a long role catalog. User screenshots show project_owner and lumen_admin grants whose real descendants should already be effective, not separately assigned.

## What Changes

- Consume the existing trusted assignable-role API's actual implied_role_ids/inherited_role_ids rather than inventing a grade hierarchy.
- Check and disable descendants of the currently selected direct parents. Recompute transitively whenever a parent changes; keep authority inherited from groups/domain separately read-only.
- Project existing group/domain inherited assignment rows into member `external_role_ids` with the same trusted current ID graph. Do not subtract original direct descendants from merged effective IDs: that loses externally granted descendants when their direct parent is removed.
- Preserve explicitly selected direct grants across parent toggles and filtering. Submit only direct selection, never auto-generated descendant IDs; do not silently revoke existing redundant direct grants.
- Add case-insensitive role name, ID and description search with localized accessible labels and empty-result feedback. Filtering does not change pending selection.
- Preserve nonowner owner/admin restrictions, busy guards, disabled group-only mutation, last-owner server protection and existing source/runtime boundaries.

## Capabilities

### New Capabilities
- project-role-selection: graph-backed inherited checkbox state, direct-only saving, external inherited authority and searchable role catalog.

### Modified Capabilities
- Existing project membership role editing presentation; no new grant policy or inferred default inheritance.

## Impact

Frontend role modal, project role types, existing member-response provenance, behavioral regression fixtures and localized catalogs. The current backend `project_service.assignable_roles` already returns trusted graph metadata through `_managed_roles`; `_member` expands only external assignment rows with the same `_expanded_role_ids` helper for the additive `external_role_ids` field. No second graph endpoint, new grant policy or DB schema convention. Architecture/design/details are updated with the actual cutover. A separate authorization change tracks the reported production Lumen403; UI selection changes do not assert downstream authorization is repaired. Shared checkouts remain untouched; work uses the isolated dev clone. Required tests, project gate and actual responsive browser interaction precede completion/archive.
