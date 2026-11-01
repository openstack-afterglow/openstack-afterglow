## Implementation Tasks

- [x] Inspect current bootstrap/importer/dispatcher contracts, deployed inputs and native automation prerequisites.
- [x] Implement lifecycle policy reconciliation with safe unique AZ repair, valid ID/name preservation, explicit-clear handling and concurrent administrator fencing.
- [x] Add precise policy failure eligibility diagnostics without weakening admission.
- [x] Keep blocked flavors inspectable and expose disabled/blocked automation readiness in administrator UI.
- [x] Exercise behavioral regressions and actual API/browser paths; build/run affected supported container architectures.
- [x] Apply bounded current-environment policy recovery and verify unchanged unrelated state; resolve or explicitly document native fleet deployment prerequisite.
- [x] Update architecture, API/operator/testing/changelog evidence.
- [ ] Stamp ARCHITECTURE review and pass full `npm run test:gate` on an isolated tree containing only reviewed changes, then archive. (Shared working tree contains unreviewed concurrent changes; not stamped.)
- [ ] Re-enable the reconciler on shared `afterglow_kolla` only after every API/admin policy writer on that DB runs this version and old writers are drained (currently paused: local backend rolled back to baseline image; candidate `afterglow-policy-backend:20261030-final`).
