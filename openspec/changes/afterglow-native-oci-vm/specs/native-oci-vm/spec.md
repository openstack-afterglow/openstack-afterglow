## ADDED Requirements

### Requirement: Preinstalled direct-service image
Afterglow SHALL provide an explicit `native-vm` target in the canonical Dockerfile that preinstalls the API, existing Notion worker, compiled frontend, Node runtime, MariaDB and Redis using the existing Python and frontend lockfiles. Its application entrypoint SHALL run as non-root without a container engine, systemd or runtime package installation. Existing deployment targets SHALL retain their contracts.

#### Scenario: Image startup
- **WHEN** the image starts with writable UID-1000-owned private state
- **THEN** it starts SQL over a private Unix socket, password-authenticated loopback Redis, the API, Notion worker and compiled frontend directly
- **AND** readiness requires the existing API and frontend HTTP liveness endpoints.

### Requirement: Preserve private state and fail safely
The native entrypoint SHALL preserve generated private credentials, operator configuration and datastore state across compatible restarts. It SHALL refuse interrupted or unmarked SQL initialization without deleting or silently adopting the existing data. Every service exit SHALL fail the supervisor; termination SHALL stop application consumers before stores within the protected stage-1 shutdown grace.

#### Scenario: Restart and child failure
- **WHEN** a ready instance is stopped and restarted with its retained private state
- **THEN** SQL/Redis data and credential identity remain unchanged
- **AND** a later datastore child exit terminates the supervisor with failure rather than reporting readiness.

#### Scenario: Interrupted SQL installation
- **WHEN** an unfinished installation or unmarked data directory exists
- **THEN** startup refuses the state and preserves it for operator recovery.

### Requirement: Distinguish image smoke from native VM acceptance
Native acceptance SHALL use the built Linux amd64 OCI archive through public Palimpsest run on a currently qualified and explicitly authorized Linux amd64/KVM host. It SHALL verify authenticated actual-root evidence, direct service processes, HTTP/browser readiness and retained-root lifecycle. Container image execution SHALL NOT substitute for native VM or authenticated OpenStack verification.

#### Scenario: Missing authorized CI prerequisites
- **WHEN** the member-only CI credential, exact resource authorization or qualified kernel/config/packer is unavailable
- **THEN** native VM acceptance remains blocked
- **AND** no administrator credential, alternate remote host or production resource is used to bypass that boundary.
