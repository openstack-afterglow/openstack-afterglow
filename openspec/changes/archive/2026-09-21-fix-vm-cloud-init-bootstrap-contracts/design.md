## Context

`generate_userdata` composes layer, GPU, and data-mount bootstrap into one cloud-config template. The current template renders layer-owned OverlayFS files and commands even when `file_storages` is empty. Instance creation similarly uses one broad managed-userdata condition for layer health-token issuance and a metadata builder that emits `union_*="none"` markers for every VM. NVIDIA DCGM bootstrap installs the daemon from apt but downloads the exporter from a GitHub release asset that is not published.

The change spans the renderer, template, sync/SSE/admin creation paths, tests, and architecture contract. Existing unrelated working-tree edits, including GitHub SSH user-data composition, must remain intact.

## Goals / Non-Goals

**Goals:**

- Make plain, GPU-only, data-mount-only, and layered bootstrap modes structurally independent.
- Keep every rendered document valid cloud-config, including an empty `packages` list.
- Restrict layer health credentials and `union_*` Nova metadata to resolved-library instances.
- Use NVIDIA-supported Ubuntu packages for DCGM and its exporter on amd64 and arm64.
- Keep sync, SSE, and administrator creation paths behaviorally aligned.

**Non-Goals:**

- Rename retained `union_*` layer metadata or guest paths.
- Change VM creation request/response schemas.
- Add new GPU driver selection policy or support non-Ubuntu images.
- Change data-mount lifecycle or Palimpsest storage topology.

## Decisions

1. **Use `file_storages` as the layer-bootstrap gate.** The renderer already receives the resolved layer storage descriptors needed by OverlayFS; this is more precise than checking strategy or generic managed user-data. The template will guard overlay setup, layer env files, manifest/envmgr files, layer health files, and layer `runcmd` entries with this condition. GPU and data-mount blocks remain separately gated.

2. **Keep `packages` present as a YAML list.** The template will render `packages: []` when no package source is active, avoiding YAML `null` while retaining cloud-init's expected type.

3. **Make resolved libraries the metadata and health ownership boundary.** Creation handlers issue health tokens only when `resolved_libs` is nonempty. The shared metadata builder always retains non-layer scheduling metadata but adds all `union_*` keys only for layered instances. Data-share metadata is appended only when layer metadata is active, matching the explicit no-`union_*` contract for data-mount-only VMs.

4. **Keep one shared metadata builder.** Sync, SSE, and admin paths call `instance_orchestration.build_instance_meta`; no path-local metadata dictionary is introduced. This prevents future drift.

5. **Install supported NVIDIA packages.** GPU bootstrap maps Debian `amd64` to NVIDIA repository `x86_64` and `arm64` to `sbsa`, rejects every other architecture, installs the CUDA keyring, then installs `datacenter-gpu-manager-4-cuda12` and `datacenter-gpu-manager-exporter`. It enables the packaged `nvidia-dcgm` and `nvidia-dcgm-exporter` services. A custom exporter binary and systemd unit are removed.

## Risks / Trade-offs

- [Existing consumers may interpret `union_*="none"` as a generic VM marker] → Treat those keys as layer-owned per the architecture contract and cover all creation paths with regressions.
- [Data-mount-only VMs lose `union_data_share_ids` metadata] → This is intentional under the approved no-`union_*` contract; data mounting itself remains cloud-init-driven and independently tested.
- [NVIDIA package/service names can change upstream] → Pin the DCGM CUDA major in the package name and verify rendered repository/package/service commands; runtime availability remains an operator-image/network concern.
- [Ubuntu/NVIDIA repository architecture names differ from Debian names] → Use an explicit case mapping and fail closed before repository download.

## Migration Plan

1. Deploy the backend/template update; no database migration is required.
2. Newly created non-layer VMs stop receiving layer artifacts and metadata. Existing Nova metadata and already-baked cloud-init are unchanged.
3. Rollback is the prior application image; no persisted schema needs reversal.

## Open Questions

None.
