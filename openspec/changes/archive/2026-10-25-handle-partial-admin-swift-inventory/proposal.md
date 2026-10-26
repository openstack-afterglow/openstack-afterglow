## Why

Read-only inspection after the first source-only report found the real Kolla configuration has ceph_rgw_swift_account_in_url=yes and the executor catalog ends in /swift/v1/AUTH_<executor>, so the guessed bare-endpoint concern does not apply here. Actual fixed-token HEADs against 57 enabled accounts returned executor204, 29 foreign204 and 27 foreign403. Failing the entire inventory on any inaccessible native account hides the readable accounts. The original screenshot500 traceback remains unconfirmed.

## What Changes

Clean-cutover the new administrator inventory response to an explicit envelope with readable items, project_count, unavailable_projects (safe denied/failed reasons) and partial. Preserve native policy, fixed credential and exact scope; never rescope, grant roles or change RGW configuration. The UI retains readable rows, suppresses global totals for partial results and exposes unavailable project names/IDs in an accessible disclosure. A fully unavailable scope is an unavailable state, not successful empty inventory. Directory and endpoint validation failures remain whole-request errors.

## Capabilities

### New Capabilities

- Explicit partial native-account visibility with safe per-project outcomes.

### Modified Capabilities

- Administrator Swift list/API, mockup and behavior tests.

## Impact

Afterglow source/UI/API/docs only; no cloud/IAM/DB/config/runtime changes. Account-in-URL and cross-account native permission are deployment prerequisites, not assumed grants. Existing cache-only model creation behavior is restored with a semantic create/reopen regression rather than exact request-copy expectations. Verify focused tests and actual local HTTP/compiled UI; keep current read-only native evidence separate from synthetic runtime evidence.
