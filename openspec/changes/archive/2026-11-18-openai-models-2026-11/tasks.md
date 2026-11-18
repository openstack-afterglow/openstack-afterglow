## 1. Implementation

- [x] Render capability-backed image options and validate size, format dependencies, and animation bounds.
- [x] Preview owned raster/vector assets, distinguish output estimates from settled run usage, and preserve idempotency and scope fences.
- [x] Add ticketed realtime translation and Live with mode-specific fields and bounded shutdown.
- [x] Preserve native catalog provenance and server-owned reasoning choices.
- [x] Update nine locale catalogs, the BFF contract, design guidance, and the architecture body.
- [x] Allow microphone requests on same-origin documents without relaxing camera, geolocation, or frame policy.
- [x] Add advanced generation/edit options and keep ordered assets scoped to the current actor.
- [x] Accept bounded realtime image frames only on admitted image sessions; keep function calling native API-only.

## 2. Verification

- [x] Run focused image, realtime, registry, and reasoning tests plus BFF and microphone header contracts.
- [x] Capture desktop and mobile browser proof against an isolated mock BFF.
- [x] Run the isolated repository gate with no private config.

The detached gate passed on `210870b858`: 15,515 backend unit, 8,524 frontend (610 files), 281 contract, and 301 functional tests. Architecture, experience catalog and Ruff passed. Browser captures in `~/.local/share/afterglow-proofs/openai-models-2026-11-18/` exercise a synthetic BFF and a fake microphone, not live provider inference or billing.

The advanced image and realtime attachment follow-up passed the detached gate on `767d25252e`: 15,515 backend unit, 8,529 frontend (610 files), 281 contract, and 301 functional tests. Architecture, experience catalog and Ruff passed. The separately run realtime BFF contract file passed 21 tests, including large-frame relay to a real loopback WebSocket. Chromium proof shows a 2,857,632-byte WebP becoming a 534,626-byte PNG carried in a 712,908-byte frame, plus SVG authoring and ordered edit-source payloads against the synthetic BFF.
