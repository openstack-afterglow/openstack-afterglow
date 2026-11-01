## Decisions
Only a successful empty database read becomes200/network_id:null. Existing configured records are unchanged; storage failures remain503. No network creation, arbitrary default selection, authentication bypass or generic404 suppression. Migrate nullable consumer types and remove the old code-specific branch. Deploy backend/frontend together.

## Verification
Existing endpoint and wizard suites plus actual Uvicorn router TCP absence/configured/storage failure/recovery smoke.
