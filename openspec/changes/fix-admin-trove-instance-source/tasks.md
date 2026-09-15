## Investigation

- [x] Trace the administrator database page from the UI through the Trove management API
- [x] Reproduce the false-empty result when the management request fails

## Implementation

- [x] Query `/mgmt/instances` through the authenticated Trove proxy and propagate failures
- [x] Render tenant Trove instances with owning project IDs and an explicit load-error state
- [x] Remove infrastructure MySQL metrics from the Trove resource page
- [x] Add backend and frontend regressions for the corrected source boundary

## Documentation and Verification

- [x] Update architecture, design, database API, and changelog contracts
- [ ] Run focused checks, responsive browser verification, architecture guards, and the full gate
- [ ] Archive the completed OpenSpec change
