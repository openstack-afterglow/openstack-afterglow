## ADDED Requirements

### Requirement: Author new builds through a Dockerfile studio
The administrator library MUST expose one Dockerfile authoring flow with inline text, local file, and safe URL inputs; pinned GitHub inputs MUST use the same job, builder, artifact, and history contract. The old independent consumer creation form MUST NOT remain a parallel new-build workflow. Existing jobs, profiles, and artifacts MUST remain browseable.

#### Scenario: Import a Dockerfile from a URL
- **WHEN** an administrator fetches a Dockerfile from an HTTP(S) URL
- **THEN** the editor is populated without starting a build, all resolved addresses and each redirect are checked for public reachability before connection, the connection is pinned to a validated address, and the response is bounded to 1 MiB

#### Scenario: Select a build target
- **WHEN** the administrator selects an SSH instance instead of a layer-only build
- **THEN** the same Dockerfile job accepts the instance's placement and SSH identity without requiring a second base-image or profile selection

### Requirement: Resolve an immutable full-root ancestor before building
A Dockerfile root FROM MUST resolve to a unique active supported Ubuntu Glance image or a sealed, digested, complete Palimpsest root lineage. A FROM-only build MUST produce a full-root squashfs from a never-booted image clone. Subsequent supported instructions MUST execute in order on the full-root lineage and seal per-step deltas with checked blob digests. The builder MUST clean resources it owns on failure.

#### Scenario: A FROM-only Dockerfile is built
- **WHEN** an administrator builds a Dockerfile containing only `FROM ubuntu:24.04`
- **THEN** a sealed full-root artifact is materialized rather than an empty step list or `/usr`-only layer

#### Scenario: A Dockerfile extends a sealed parent
- **WHEN** FROM names a sealed Palimpsest digest with a complete full-root ancestor chain
- **THEN** child instructions execute over that lineage and their artifacts retain the base-image and parent provenance

#### Scenario: A Dockerfile names an unusable base
- **WHEN** FROM names an absent or ambiguous Glance image, an unsealed parent, or a legacy partial-root chain
- **THEN** the build is rejected before provisioning side effects and explains the unusable reference

### Requirement: Reuse only verified Dockerfile build prefixes
The build cache MUST derive step keys from the verified parent blob lineage and normalized instruction arguments, reuse only a contiguous sealed prefix, and resume new steps after the first miss. Inline and GitHub sources MUST follow the same cache and terminal-job contract.

#### Scenario: Cache hit followed by miss
- **WHEN** the root and first step match sealed digests but a later step differs
- **THEN** only the matching prefix is reused and remaining steps are built over its last artifact

### Requirement: Boot a full-root consumer with durable private state
A Dockerfile consumer MUST mount the full-root squashfs and child-first read-only deltas as the lower root, with a dedicated writable Cinder ext4 upper/work volume identified by serial and filesystem UUID. It MUST not format a boot disk or unverified disk. Guest readiness MUST require successful overlay activation on the real root and an actual health signal; merely reaching Nova ACTIVE MUST NOT report success. Legacy unlayered, `/usr`-layer, GPU, and data-volume creation MUST continue to use their appropriate flows.

#### Scenario: Reboot an SSH-ready consumer
- **WHEN** a created Dockerfile VM is rebooted after writing to its overlay root
- **THEN** the root still includes the base filesystem and ordered deltas, the writable changes persist, and the health path confirms activation

#### Scenario: Cinder volume identity cannot be verified
- **WHEN** the attached nonboot disk is missing, ambiguous, formatted, or not the expected serial
- **THEN** first-boot provisioning fails closed before formatting any disk
