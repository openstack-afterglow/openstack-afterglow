## Why

Lumen's local Compose services could start without the Keystone values used by Afterglow, causing valid forwarded browser sessions to fail with authentication errors. The documented startup contract also needed to load both the base and separated-service environment files consistently.

## What Changes

- Document the required dual env-file Compose invocation.
- Load the shared `.env` file for Lumen migrate, API, and worker containers.
- Resolve `KEYSTONE_*` values from explicit `LUMEN_KEYSTONE_*` settings first, then existing `OS_*` fallbacks, without localhost authentication defaults.
- Preserve connection-project and delegated target-project headers as separate trusted BFF values.
- Add contract coverage and a real local Compose startup check.

## Capabilities

### New Capabilities

- `lumen-compose-auth`: Defines fail-closed Keystone configuration and project-scope forwarding for the local Lumen Compose boundary.

### Modified Capabilities

None.

## Impact

- `docker-compose.yml` and `.env.example`
- `backend/app/services/service_proxy.py`
- `backend/tests/contracts/test_lumen_proxy.py`
- Local separated-service startup documentation and operator workflow
