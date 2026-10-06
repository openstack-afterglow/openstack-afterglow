## Why

The existing local Afterglow VM proof booted an Ubuntu VM and ran Docker Compose inside it. The user selected Linux amd64/KVM OCI-root instead: build the application filesystem once, then boot that filesystem as the VM's actual `/`, with required packages already present and no container engine in the guest.

## What Changes

- Add an explicit `native-vm` target to the canonical root Dockerfile, reusing the backend and compiled frontend stages while installing MariaDB/Redis and the API plus worker dependency graph.
- Add a non-root application supervisor compatible with Palimpsest's protected stage-1 PID 1. It directly initializes and runs local MariaDB/Redis, FastAPI, compiled SvelteKit, and the existing Notion worker without systemd, Docker, or privileged operations.
- Generate per-root private secrets/configuration on first execution, preserve data/configuration on compatible retained-root reuse, bind database/cache to guest loopback, and publish only explicit application endpoints.
- Qualify the actual artifact and real application startup locally before a separately scoped Linux KVM launch. OCI-root qualification requires public `run`, authenticated `oci root-proof`, actual HTTP/browser readiness, guest process/package evidence, and safe owned stop/removal. A Docker execution smoke is not OCI-root proof.

## Impact and Boundaries

Existing Docker/Compose/Kubernetes/Kolla deliverables and external sibling-service ownership remain unchanged. The new target is explicit, not the Dockerfile default. No secrets are copied into the image. No production OpenStack credentials, admin-project substitution, cloud resource creation, private helper execution, publication, commit/push, or shared-resource mutation is authorized by this change. Linux target readiness and exact execution approval must be established before any native launch; the historical member-only CI credential blocker is not bypassed.

Linux amd64 is the OCI-root runtime acceptance target. ARM64 image builds may prove image portability, not an unsupported ARM64 OCI-root runtime. Real OpenStack login/resource operations remain distinct from local application/DB/cache readiness.
