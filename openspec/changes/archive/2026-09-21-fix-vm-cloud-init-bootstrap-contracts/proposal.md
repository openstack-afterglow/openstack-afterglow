## Why

Managed cloud-init currently treats GPU-only and data-mount-only VMs as layered VMs, emitting unusable OverlayFS artifacts, layer health credentials, and `union_*` Nova metadata. GPU bootstrap also downloads a release tarball that NVIDIA does not publish, so otherwise valid GPU instances can fail during first boot.

## What Changes

- Render legacy OverlayFS, env, manifest, health, and layer `runcmd` artifacts only when layer file storage exists.
- Keep GPU bootstrap and user data-mount bootstrap independent from layer bootstrap, with schema-valid empty package lists.
- Issue layer health tokens and emit `union_*` Nova metadata only for instances with resolved libraries, consistently across sync, SSE, and admin creation paths.
- Install DCGM and its exporter from NVIDIA's supported Ubuntu packages, with explicit `x86_64` and `sbsa` repository mapping and fail-closed unknown architecture handling.
- Add regressions for plain, GPU-only, data-mount-only, and layered creation modes.

## Capabilities

### New Capabilities
- `vm-cloud-init-bootstrap`: Defines mode-specific VM bootstrap rendering, layer metadata ownership, and supported NVIDIA DCGM package installation.

### Modified Capabilities

None.

## Impact

- Backend cloud-init rendering and templates.
- Sync, SSE, and administrator Nova instance creation metadata/token behavior.
- VM creation regression tests, architecture documentation, and changelog.
- No API request or response schema change; existing non-layer VMs stop receiving layer-owned artifacts and metadata.
