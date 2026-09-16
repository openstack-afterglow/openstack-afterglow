## Why

Afterglow file logging has environment-specific paths and incompatible rotation behavior. The backend currently uses Python’s independent time-or-size handlers; the frontend only has process output. Docker Compose and Kolla can mount directories, while Kubernetes has no writable file-log mount. This prevents a consistent, inspectable log naming and retention contract.

## What Changes

- Replace backend file rotation with a date-and-size handler that appends JSON records to `backend-YYYY-MM-DD.log` and allocates `backend-YYYY-MM-DD-01.log`, `-02.log`, and so on before a record would exceed the configured byte limit. Existing files are never renamed or overwritten.
- Add a frontend PID-1 runner that mirrors Node stdout/stderr to their original streams and independently writes `frontend-YYYY-MM-DD.log` with the same date-and-size sequence behavior.
- Make `/app/logs` the portable default log directory, bind it to the repository `logs/` directory for local Docker Compose, preserve Kolla’s existing component directories through environment overrides, and mount a pod-local `emptyDir` at `/app/logs` in static Kubernetes and Helm workloads.
- Migrate logging configuration from a single output filename and mutually exclusive rotation modes to an explicit log directory and maximum byte size. Standard config, example config, Kolla templates, and K8s rendering use the same contract.
- Add deterministic backend and frontend rotation tests plus Compose/Kolla/Kubernetes manifest contracts.

## Capabilities

### New Capabilities

- Backend and frontend create date-local, size-sequenced log files without overwriting prior files in local, Compose, Kolla, and Kubernetes runtimes.
- Application stdout/stderr remains available to Docker and Kubernetes collectors while frontend output is also written to its file sink.

### Modified Capabilities

- Kubernetes pods gain an explicit writable but ephemeral application log volume; no PVC persistence is implied.
- Kolla uses the portable frontend runner instead of a shell redirection while retaining its `kolla_logs` volume layout.

## Impact

The change updates application logging, runtime entrypoints, Compose/Kolla/Kubernetes mounts, configuration examples, and focused contracts. It does not introduce host bind mounts outside Compose, extra Kolla volumes, or a Kubernetes PVC contract.
