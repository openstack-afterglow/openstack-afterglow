## Why

Native telemetry is now readable in Afterglow, but administrators cannot manage Aodh alarms or independently inspect the Gnocchi storage/ingestion service. Operators need native alarm definitions and notification actions, with truthful service and permission diagnostics.

## What Changes

- Add administrator Aodh dashboard, paged alarms, detail/history, create/edit/delete and enable/repeat-action settings.
- Provide standard native notification actions (HTTP(S) webhook, trust HTTP(S), log, Zaqar and trust Heat), with deployment-support caveats; never execute webhook requests from Afterglow.
- Add a separate read-only Gnocchi service inspection page for status/backlog, capabilities, archive policies/rules, resource types, resources, metrics and bounded measures.
- Reuse caller Keystone catalog/session and administrator authorization, private no-store responses and existing console primitives/localization. Preserve existing monitoring when native services are absent.

## Capabilities

### New Capabilities
- `admin-native-telemetry`: Administrator native alarm management and independent Gnocchi service inspection.

### Modified Capabilities
None.

## Impact

Backend administrator routers/services and endpoint tests; frontend administrator routes/navigation/API contracts and four locale catalogs; architecture/API/deployment/testing documentation. No schema, dependency, service credential, collector, native configuration mutation or production deployment.
