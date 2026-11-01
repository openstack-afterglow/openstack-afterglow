## Implementation Tasks

- [x] Generate new CPU native flavor names as `cpu.{vcpus}c_{ramGiB}g`, preserve deterministic IDs and handle native-name conflicts without mutating occupants.
- [x] Preserve existing owned native IDs, hardware and names while projecting the canonical CPU display name separately; never use a display label as a native identifier, quota key or authorization proof.
- [x] Automatically include existing and new manually created, verified CPU flavors under Afterglow policy and private project-access reconciliation with persistent ownership, safe readback, graph fencing and unknown-outcome handling; do not infer uncertain GPU/PCI roles or alter immutable fields.
- [x] Preserve public Nova visibility, legacy VM references, custom hardware specifications and description; distinguish Afterglow admission from direct Nova access and report unsupported/unknown cases.
- [x] Present canonical names consistently in admin, VM creation/resize and existing-instance surfaces while retaining raw native identity where operators need it.
- [x] Update affected architecture, reference and user documentation and regression tests; verified actual execution using isolated synthetic native services and browser surfaces.
- [x] Complete scoped verification and archive without modifying production or unrelated shared state. Full gate stops at stale shared architecture marker; live cloud and guest acceptance remain unverified.
