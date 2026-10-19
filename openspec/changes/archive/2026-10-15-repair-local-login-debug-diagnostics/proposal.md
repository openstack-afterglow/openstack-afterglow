## Why

The running local Docker backend records password-login responses after 275–754 seconds, including 409 and 503 failures, without an actionable authentication error. Its effective debug setting is false: the mounted private `.local-services/afterglow.conf` lacks `[DEFAULT] debug`, while the root configuration contains invalid TOML `debug = True`. `AuthRoute` consumes HTTP exceptions before the global exception logger. Native failures are therefore invisible beyond request duration/status.

## What Changes

- Diagnose the live local authentication dependency path using bounded, credential-safe, read-only native requests; repair the demonstrated cause without relaxing domain, project, system, or inherited-role authorization.
- Restore valid debug configuration in the actual local mounted configuration, retaining the private snapshot, credentials, database state and volumes.
- Emit bounded structured authentication function/stage outcomes and safe exception causes/statuses in debug logs. Do not log passwords, tokens, raw HTTP traffic, exception messages, request bodies or exception locals.
- Cover failure diagnostics and any corrected authority behavior with focused regressions; build affected canonical images for declared architectures and verify the authorized local deployment and real login path.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- Local password login: working native authentication with live authority checks and actionable safe diagnostics.
- Application debug logging: identify the failing authentication stage and structural native cause while preserving credential redaction.

## Impact

Backend identity/authentication services, logging helpers and regression coverage; private local debug configuration; existing architecture/development/testing documentation. No new permission model, native grant migration, production deployment, secret rotation, data deletion, or authentication-policy bypass.
