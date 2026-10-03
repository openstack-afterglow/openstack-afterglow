## Why

Lumen's text-only model catalog, run APIs, and accounting cannot safely serve image generation, finite audio, or realtime voice. Afterglow needs the corresponding authenticated workflows without owning provider keys, model execution, assets, or the authoritative run journal.

## What Changes

- Register separate text, image, TTS, STT, and realtime model kinds with explicit unit pricing, direct-provider eligibility, and capability/readiness gates. No unsupported route, missing price, or subscription credential may be advertised executable.
- Execute image generation and editing through owned assets and idempotent durable work; expose native and OpenAI image APIs, exact variant billing, and authenticated Afterglow image workflows.
- Add finite speech synthesis and transcription, bounded streaming/asset handling, scoped usage accounting, compatible SDK surfaces, and Afterglow audio workflows.
- Add separately scoped realtime voice sessions with OpenAI/Google provider protocols, an authenticated Afterglow WebSocket relay, privacy controls, and usage settlement; no generic audio/video shortcut.
- Keep the existing text-chat path unchanged. Migrate callers cleanly, update architecture/operations/SDK documentation and runnable examples, and distinguish synthetic verification from live provider acceptance.

## Capabilities

### New Capabilities

- Durable multimodal image/audio execution and realtime voice with explicit per-unit pricing, project ownership, and API-key scopes.
- Afterglow image Studio, audio and microphone UX over authenticated Lumen BFF paths.

### Modified Capabilities

- Lumen model registry, provider routing, run journal and credit ledger; Afterglow chat administration and selected chat flows.

## Impact

Lumen MariaDB migrations, provider transports, assets, API/worker/SDK, and Afterglow SvelteKit chat administration/studio, backend BFF relay, tests and docs. Preserve unrelated dirty source and unresolved merge markers. No deployment, publication, production provider proof, or credential use is implied by a passing synthetic suite.
