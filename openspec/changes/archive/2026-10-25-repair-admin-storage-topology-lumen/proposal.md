## Why

Administrator screenshots report Object Storage listing failing with an internal-server error; the network topology lacks domain parent groups; Lumen needs multiple provider credentials with explicit per-key connection checks; model-kind creation/filtering and correction are unreliable or unavailable.

## What Changes

- Trace and repair administrator Swift account/container listing with the existing system-authority, native-policy and domain/project inventory boundaries intact.
- Add administrator domain-owned parent boxes around network zones in canvas/lane views where applicable. Group by native project→domain IDs, disambiguate duplicate names and retain explicit unknown ownership. Domain grouping does not assert connectivity or synthesize network links.
- Reuse the current endpoint→account→credential Lumen implementation for multiple keys. Add an explicit bounded selected-key connection probe: structured JSON ping/pong where supported, plain ping when structured output is unsupported. Show timestamp, selected model/mode and sanitized outcome; never return secrets, rotate keys, or retry ambiguous/provider/auth failures.
- Preserve selected model_kind through creation, discovery review, returned catalog and registered-model filtering. Add an owner-fenced editor to correct an existing model kind without deleting/recreating its identity, with server readiness/pricing validation.

## Capabilities

### New Capabilities

- Domain parent grouping in the administrator network topology.
- Explicit per-credential provider connectivity checks.
- Registered model-kind correction.

### Modified Capabilities

- Administrator object-storage inventory.
- Lumen provider credential management and model-kind persistence/filtering.

## Impact

Afterglow frontend, affected FastAPI BFF/Swift APIs and tests; native Lumen source only if its existing account/probe/model contract requires a change, tracked in its own change. Reuse current UI primitives and all supported locale catalogs. Shared checkout/index, config, credentials, databases and running services are preserved. No commit, push, release, production mutation or deployment is authorized. Acceptance requires focused behavior checks and real local HTTP/compiled-browser exercises; synthetic identity/provider boundaries remain explicitly distinguished from live provider/cloud acceptance.
