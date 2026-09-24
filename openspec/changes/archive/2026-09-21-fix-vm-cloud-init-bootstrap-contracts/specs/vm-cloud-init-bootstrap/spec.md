## ADDED Requirements

### Requirement: Bootstrap modes remain independent
The system SHALL render layer-owned guest files, layer health units, manifest configuration, and layer startup commands only when layer file storage is present. GPU bootstrap and user data-mount bootstrap SHALL remain independently available without layer bootstrap.

#### Scenario: Plain VM bootstrap
- **WHEN** cloud-init is rendered without layer file storage, GPU support, or data mounts
- **THEN** the document contains no layer-owned OverlayFS, environment, manifest, health, or startup artifacts

#### Scenario: GPU-only VM bootstrap
- **WHEN** cloud-init is rendered with GPU support and without layer file storage
- **THEN** the document contains GPU bootstrap and contains no layer-owned OverlayFS, environment, manifest, health, or startup artifacts

#### Scenario: Data-mount-only VM bootstrap
- **WHEN** cloud-init is rendered with user data mounts and without layer file storage
- **THEN** the document contains data-mount bootstrap and contains no layer-owned OverlayFS, environment, manifest, health, or startup artifacts

#### Scenario: Layered VM bootstrap
- **WHEN** cloud-init is rendered with layer file storage
- **THEN** the document contains the layer OverlayFS and environment bootstrap required to mount the resolved library stack

### Requirement: Cloud-config packages type is stable
The system SHALL render the cloud-config `packages` field as a YAML list in every bootstrap mode.

#### Scenario: No packages are required
- **WHEN** no layer, GPU, dynamic-install, CephFS, NFS, or data-mount package is required
- **THEN** parsed cloud-config contains `packages: []` rather than `packages: null`

### Requirement: Layer credentials and Nova metadata follow layer ownership
The system SHALL issue layer health-report credentials and emit `union_*` Nova metadata only when resolved libraries are nonempty. Sync, SSE, and administrator instance creation SHALL use the same metadata rules.

#### Scenario: Non-layer instance creation
- **WHEN** a plain, GPU-only, or data-mount-only instance is created
- **THEN** no layer health token is issued and the Nova metadata contains no key prefixed with `union_`

#### Scenario: Layered instance creation
- **WHEN** an instance is created with resolved libraries
- **THEN** layer health-token issuance is attempted and the Nova metadata records the resolved layer bootstrap fields

### Requirement: Supported NVIDIA DCGM installation
The system SHALL install DCGM and its exporter from NVIDIA's Ubuntu package repository using `datacenter-gpu-manager` and `datacenter-gpu-manager-exporter`. It SHALL NOT depend on a GitHub release tarball for the exporter.

#### Scenario: AMD64 GPU bootstrap
- **WHEN** GPU bootstrap runs on Debian architecture `amd64`
- **THEN** it uses the NVIDIA repository architecture `x86_64`, installs both supported packages, and enables the packaged services

#### Scenario: ARM64 GPU bootstrap
- **WHEN** GPU bootstrap runs on Debian architecture `arm64`
- **THEN** it uses the NVIDIA repository architecture `sbsa`, installs both supported packages, and enables the packaged services

#### Scenario: Unknown GPU architecture
- **WHEN** GPU bootstrap runs on any other architecture
- **THEN** it exits with an error before constructing or downloading an NVIDIA repository URL
