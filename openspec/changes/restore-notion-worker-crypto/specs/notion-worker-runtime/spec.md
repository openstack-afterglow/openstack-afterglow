## ADDED Requirements

### Requirement: Repository-owned crypto dependency
The backend and Notion worker environments MUST resolve `afterglow-crypto` from the repository-owned `services/afterglow-crypto` package, and the installed distribution MUST remain usable after build-only source directories are absent.

#### Scenario: Worker-only dependency installation
- **WHEN** the worker environment is created with only the `worker` dependency group
- **THEN** `afterglow_crypto` is installed as a regular distribution
- **AND** `app.services.k3s_crypto` imports successfully

#### Scenario: Backend dependency installation
- **WHEN** the backend environment is created from the project dependencies
- **THEN** it resolves the same repository-owned crypto package rather than a separate remote source

### Requirement: Final worker image crypto contract
The final `worker` image MUST prove the Notion encryption boundary from inside the runtime image before publication or deployment.

#### Scenario: Image smoke succeeds
- **WHEN** the worker image smoke runs with disposable encryption keys
- **THEN** the final image imports the crypto package
- **AND** a Notion configuration encryption/decryption round trip returns the original plaintext

#### Scenario: Crypto package is omitted
- **WHEN** a worker image does not contain the crypto distribution
- **THEN** the image smoke fails with a non-zero exit status
- **AND** the image is not eligible for deployment

### Requirement: Immutable Kolla worker rollout
A production recovery MUST deploy the verified worker image by immutable digest through the existing Kolla-Ansible service lifecycle and MUST NOT change unrelated backend or frontend image references.

#### Scenario: Worker recovery rollout
- **WHEN** a verified Linux amd64 worker image has been published
- **THEN** the operator records its manifest digest in `afterglow_worker_image_ref`
- **AND** runs Afterglow-scoped Kolla prechecks before the rollout
- **AND** each intended worker container runs the expected image digest without a restart loop

#### Scenario: Rollout prerequisite fails
- **WHEN** image publication, host identity verification, Kolla prechecks, or image pull fails
- **THEN** the rollout stops before claiming recovery
- **AND** no host-key verification bypass or mutable production image reference is introduced

### Requirement: Live Notion recovery verification
The deployment MUST be considered recovered only after the actual synchronization contract succeeds.

#### Scenario: Due target synchronizes
- **WHEN** the enabled target is overdue after the worker rollout
- **THEN** worker logs record successful target synchronization without the missing-module error
- **AND** `notion_targets.last_sync` advances beyond its pre-rollout value
- **AND** the administrator-visible timestamp reflects the new value

#### Scenario: Container runs but synchronization fails
- **WHEN** the worker container is running but the target completion log or timestamp advancement is absent
- **THEN** recovery is reported as failed or incomplete
