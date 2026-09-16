## Why

Chat uploads already use Lumen's canonical asset API, but the UI does not explain the automatic project storage behavior, generated artifacts are not surfaced as a durable storage contract, API examples cannot be copied directly, and automatic memory extraction is presented only as manual memory cards.

## What Changes

- Keep attachment upload automatic at file selection and expose the project-owned object-storage destination in the composer.
- Render generated file artifacts as durable downloadable chat files backed by Lumen assets.
- Add explicit copy actions for OpenAI and Anthropic connection examples.
- Present the automatically maintained memory set as a readable `memory.md` document while retaining scoped item controls.
- Prevent hidden slash or at-sign shortcuts from dispatching while a response is streaming.

## Capabilities

### New Capabilities

- `chat-project-assets`: Project-owned automatic storage and durable generated-file presentation in chat.
- `chat-memory-document`: Human-readable Markdown projection of automatically extracted user memory.

### Modified Capabilities

- `chat-api-connection-guide`: Copyable SDK connection examples using server-discovered public endpoints.

## Impact

The frontend chat composer, message rendering, settings overlay, API-key manager, client contracts, tests, and Lumen named test target change. Afterglow remains an authenticated BFF/UI boundary; object persistence and memory extraction remain owned by Lumen.
