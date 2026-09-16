## Implementation Tasks

- [x] Replace backend file-handler configuration with a locked date-and-size `backend-YYYY-MM-DD[-NN].log` handler, migrate configuration to log directory and byte limit, and add deterministic backend rotation tests.
- [x] Add a frontend PID-1 file-log runner that tees Node stdout/stderr and writes independent `frontend-YYYY-MM-DD[-NN].log` files without overwriting existing files.
- [x] Update production and development Docker entrypoints, Compose mounts, repository log-directory tracking, and Kolla environment/configuration so both services use the portable sinks while Kolla retains component directories.
- [x] Add writable pod-local `/app/logs` emptyDir mounts and appropriate security context to static Kustomize and Helm backend/frontend workloads; retain stdout/stderr and document that the volume is ephemeral.
- [x] Add and run backend, frontend, Compose, Kolla, Kustomize, and Helm regression contracts for rotation naming, size/date boundaries, storage mounts, and stream preservation.
