## Why

The existing Image/Audio Studio pages expose dense side-by-side forms rather than the image-first Gemini and writing-first ElevenLabs workflows requested by the user. TTS already returns owned audio bytes, but STT drops every field except text and has no timestamped download.

## What Changes

- Recompose Image Studio around a central prompt composer, generation/edit choice, attachment preview, capability-backed options, original style thumbnails that append visible prompt instructions, and owned results/downloads. Preserve durable run history, cancel, scope isolation, pricing/readiness and idempotency.
- Recompose Audio Studio into TTS/STT tabs. Use a broad text editor and a desktop settings column for actual model/voice/format options. Preserve actual Blob playback/downloads and request fencing.
- Add STT file selection/drop and source preview, real timestamped transcript display, copy/chat handoff and UTF-8 TXT/SRT export. Never invent timestamps, historical rows, waveforms, voices or generation output.
- Extend the canonical local Lumen source (`../lumen`, the Compose build context) narrowly so native STT can request segment timestamps on direct OpenAI whisper-1, expose supported granularity through capabilities, freeze the intent, persist provider segments in the durable result and return them to the authenticated browser. Other supported STT models remain plain-text capable with an explicit timestamp-unavailable explanation.
- Fix in-browser playback: the frontend CSP had no `media-src`, so `default-src 'self'` blocked object-URL audio; allow only `media-src 'self' blob:`. Localize the audio breadcrumb segment (`LUMEN / 오디오`).

## Capabilities

### New Capabilities

- Timestamped native STT result and client-side TXT/SRT download from actual provider time ranges.
- Prompt-based visual style selection from original locally hosted image assets.

### Modified Capabilities

- Existing image generation/editing and finite TTS/STT presentation, not new video generation, realtime voice or ElevenLabs transport.

## Impact

Afterglow frontend media components/client/types/tests/assets and affected architecture/design/API docs; canonical Lumen native audio API, capability projection, direct audio transport and durable result plus focused tests/docs. No schema migration, dependency change, authentication bypass, configured credential/model mutation, paid application inference, production deployment, commit or push. Preserve all pre-existing dirty work in both repositories. Browser provider/auth fixtures are explicit evidence limits, not provider-real acceptance. Verify dark/light and 390/767/768/1023/1024/1440px; use the existing semantic tokens and UI primitives. Generated references/assets are design tooling only and are not real user media results.
