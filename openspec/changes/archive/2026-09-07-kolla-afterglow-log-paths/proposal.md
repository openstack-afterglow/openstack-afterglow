## Why

The Afterglow role mounts Kolla's existing `kolla_logs` Docker volume at `/var/log/kolla`, but a mount does not create writable component directories or redirect frontend process output. The backend’s file handler targets a root-owned volume path and silently falls back to stdout on `OSError`; the frontend has no file logger. Consequently the expected host paths under `/var/lib/docker/volumes/kolla_logs/_data/` remain absent or empty.

## What Changes

- Create writable `afterglow_api` and `afterglow` directories inside the existing `kolla_logs` volume before Afterglow services start, using a disposable root container and group-write permissions compatible with the unprivileged runtime users.
- Set the portable backend log directory to `/var/log/kolla/afterglow_api`, where date-and-size rotation writes `backend-YYYY-MM-DD[-NN].log`.
- Start the frontend through the portable PID-1 tee runner with `/var/log/kolla/afterglow` as its log directory, producing `frontend-YYYY-MM-DD[-NN].log` while preserving stdout and stderr.
- Keep the named volume mounted at `/var/log/kolla`; do not create host bind mounts or a second Docker volume.
- Add Kolla contracts for setup ordering, mount destinations, writable permissions, and concrete backend/frontend log sinks.

## Capabilities

### New Capabilities

- Kolla hosts persist date-and-size sequenced backend logs under `kolla_logs/_data/afterglow_api/` and frontend logs under `kolla_logs/_data/afterglow/`.

### Modified Capabilities

- Afterglow config/reconfigure lifecycle prepares log directories before service containers run.

## Impact

The custom Afterglow Kolla role provides the volume and component-directory adaptation. The portable application log rotation change owns file naming and stream behavior; Docker's existing `kolla_logs` volume remains authoritative.
