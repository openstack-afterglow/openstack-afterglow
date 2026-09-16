## Investigation

- [x] Capture read-only latency profiles for representative user and administrator API flows.
- [x] Trace the slow frontend request lifecycle through backend and OpenStack client calls.
- [x] Confirm the root cause with a deterministic reproduction or request-count/timing evidence.

## Implementation

- [x] Fix only the confirmed latency bottleneck without changing authorization or freshness semantics.
- [x] Add behavior-focused regression coverage that fails on the prior bottleneck.

## Verification

- [x] Re-run the exact slow scenario and compare before/after timings and request counts.
- [x] Run focused targets, frontend/backend checks as applicable, and `npm run test:gate`.

## Completion

- [x] Update relevant documentation or changelog when behavior changes.
- [x] Complete this checklist and archive with `openspec archive reduce-backend-communication-latency --skip-specs --yes`.
