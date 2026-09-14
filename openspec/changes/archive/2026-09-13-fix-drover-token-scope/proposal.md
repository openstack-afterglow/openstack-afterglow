## Why

The requested local DMSLAB dashboard fails at two distinct boundaries. Nova server-list/quota calls receive upstream 503. Separately, Drover SDK stats return 401 for the affected user's valid DMSLAB-scoped token, which Afterglow reports as HTTP 200 with `available: false`. Drover `validate_token()` reauthenticates tokens without an explicit project header, losing their existing scope or switching administrators to their default project. Real requests prove no-header 401 versus explicit-project 200; Keystone token introspection preserves the original project and returns 200.

## What Changes

- Validate an incoming Drover token through Keystone introspection when no explicit target project is requested. Preserve its original token, project and roles. Retain Keystone-authorized explicit rescoping and all fail-closed/admin/ownership checks.
- Add behavioral regressions for original-scope preservation, an unscoped token and failed validation.
- Require actual Drover availability and valid counts in the existing local dashboard smoke, not just HTTP 200.
- Rebuild/recreate only the affected local Drover API/worker, then exercise the affected user's read-only dashboard path and check actual OpenStack destinations.

## Impact

Drover authentication source/tests/reference documentation in the sibling repository; Afterglow local smoke and deployment/architecture records. No OpenStack resource, catalog, role assignment, credential, database migration, volume or remote service mutation. Nova restoration requires separately authorized upstream access; do not hide its failure or claim complete dashboard recovery.
