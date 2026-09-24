## 1. Bootstrap Implementation

- [x] 1.1 Gate layer template artifacts and health rendering on layer file storage while preserving independent GPU and data-mount bootstrap
- [x] 1.2 Render the cloud-config packages field as a YAML list in every mode
- [x] 1.3 Gate layer health-token issuance and all `union_*` Nova metadata on resolved libraries across sync, SSE, and admin creation
- [x] 1.4 Replace the DCGM exporter tarball flow with supported NVIDIA packages and fail-closed repository architecture mapping

## 2. Regression Coverage

- [x] 2.1 Replace the obsolete GPU truth-table test with renderer and handler behavior assertions
- [x] 2.2 Add parsed cloud-config regressions for plain, GPU-only, data-mount-only, and layered modes
- [x] 2.3 Add sync, SSE, and admin Nova metadata and health-token regressions

## 3. Documentation

- [x] 3.1 Document VM layer bootstrap ownership boundaries in `ARCHITECTURE.md`
- [x] 3.2 Add an Unreleased changelog entry for the cloud-init and DCGM fixes

## 4. Verification

- [x] 4.1 Run focused cloud-init, GPU, no-library, and admin instance suites
- [x] 4.2 Smoke-render all bootstrap modes and validate cloud-config plus NVIDIA distribution contracts
- [x] 4.3 Stamp the architecture review and run the complete repository test gate
- [x] 4.4 Run the staged architecture guard without disturbing unrelated staged work
- [x] 4.5 Assess live OpenStack VM smoke availability and run it when credentials and capacity exist (not run: disposable live image/flavor/SSH/user prerequisites are absent)
