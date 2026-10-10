## Why

The development Compose manifest accepts generic service database environment overrides even though its documented contract requires private local datastores. A plain `docker compose -f docker-compose.dev.yml up --build` loads repository `.env`, sending Drover, Waygate and Lumen migrations to remote Kolla databases and causing ProxySQL authentication failures. Palimpsest bootstrap can also reach a remote database successfully, so this is an isolation defect rather than a reason to change credentials or delete local volumes.

## What Changes

- Restore literal local `DATABASE_URL` values in the five shared development environment anchors; API, worker and migration/bootstrap commands inherit the same local destination.
- Exercise real Compose configuration resolution with hostile synthetic `.env` and shell values through plain and explicit private-env-file entry paths.
- Back up existing local databases and recover the canonical stack without modifying `.env`, configuration snapshots, encryption keys, persistent volumes, migration hashes or remote databases.
- Record local startup evidence and the limit that an earlier remotely routed Palimpsest bootstrap's exact effects are not established by its exit code.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-runtime-security`: development datastore destinations remain isolated regardless of generic database overrides in `.env` or the process environment.

## Impact

Only the source-development manifest and its regression coverage change runtime behavior. Production/minimal Compose, native service code, OpenStack authentication, service endpoint overrides, schemas and credentials are unchanged. Local MariaDB/PostgreSQL/Redis volume identities and keys are preserved. Direct development Compose still requires prepared private credentials and callback inputs for full startup; fixing database isolation does not introduce insecure defaults.
