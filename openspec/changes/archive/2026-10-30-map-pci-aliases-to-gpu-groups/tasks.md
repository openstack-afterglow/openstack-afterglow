## Implementation Tasks

- [x] Extract only PCI alias declarations from effective Kolla Nova API configuration with provenance and explicit unavailable/conflict states; preserve secrets and independent deployments.
- [x] Expose administrator-only PCI alias and Placement inventory observations, including allocated, unmapped, unknown and partial states.
- [x] Distinguish GPU, audio and unknown candidates and let an administrator create explicitly approved multi-alias groups without JSON entry.
- [x] Generate requested GPU group/count flavor names while preserving existing immutable flavors and resolving native name collisions safely.
- [x] Project the canonical group name consistently into domain pool and GPU quota without changing resource-class accounting or native quotas.
- [x] Preserve GPU guest initialization after pooled admission without writing a legacy GPU reservation.
- [x] Verify exact backend routes, state boundaries, real synthetic HTTP and administrator browser flows; update architecture, guides, changelog and verification evidence. Live Nova/guest/physical census and production deployment remain unverified; shared full gate stops at the stale architecture marker.
- [x] Complete the OpenSpec checklist and archive after scoped verification.
