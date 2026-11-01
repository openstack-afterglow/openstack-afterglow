## Implementation Tasks

- [x] Reproduce a normal native-token refresh overlapping GPU request creation, listing and review using the actual session-store CAS.
- [x] Exclude renewable token bytes from the stable session signature while continuing to reject missing/blacklisted/malformed sessions and changed scope/provider identity.
- [x] Verify the overlap and negative security cases, run related regression targets and document source-only/operational boundaries without shared state mutation.
- [x] Archive the completed change after verification. Full gate remains blocked by the pre-existing shared architecture snapshot; no deployment or shared-DB mutation.
