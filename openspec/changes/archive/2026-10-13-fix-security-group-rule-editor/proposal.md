## Why

Security-group editing currently exposes manual remove/add controls and opens the editor below the entire rule list. The add flow also keeps a duplicate add trigger visible. The requested interaction is a conventional save/cancel editor immediately below the selected rule, with one add action when creating a rule.

## What Changes

- Replace manual remove/recreate controls with Save and Cancel. Save uses the existing project-scoped POST/DELETE endpoints; Neutron rule fields remain immutable. When quota permits, create the replacement before deleting the old rule; an unchanged draft performs no writes. At a full quota, validate before removal and attempt restoration if creation fails.
- Keep rule creation separate from editing and hide the top add trigger while a form is open.
- Render the edit form immediately below its selected rule; keep the new-rule form after the list. Preserve responsive form width within the table's scroll viewport.
- Preserve existing quota and validation boundaries, validate CIDR/IP-version and mutually exclusive targets before any mutation, capture credentials/project and original fields, and distinguish creation failure, failed restoration, and failed old-rule removal. Keep the draft when creation fails.
- Update all four locale catalogs and meaningful behavior regressions. No endpoint, schema, dependency, authentication, or deployment change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Project security-group rule editing and creation interactions.

## Impact

The existing security-group route, rules panel, shared rule form, locale catalogs, and their consumer-visible tests change. Replacement is not atomic: create-first temporarily overlaps policies; a full quota requires removal-first, a visible access-policy warning, and best-effort restoration on failure. Failed old-rule removal leaves the newly created rule visible and reports partial application rather than claiming success. Existing concurrent work and the real Git index are preserved. Verification is local compiled UI with synthetic API/identity fixtures, not live Neutron or deployment acceptance.
