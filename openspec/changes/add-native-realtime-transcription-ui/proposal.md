# Native realtime transcription in the existing voice surface

## Scope
Extend the existing `/dashboard/chat/realtime` surface, linked from Audio Studio, to support authoritative `realtime_kind=transcription` capabilities as well as existing conversation voice. No general Studio redesign, automatic model re-kind, price inference or provider/production calls.

## Contract
- Native signed-ticket POST uses optional `kind=transcription`, null voice and the existing scoped endpoint; native Lumen admission must explicitly support it.
- Transcription requires priced native input, 24000-Hz PCM input and zero output, not conversation voices or audio output.
- Explicit user microphone permission precedes admission. Existing owner/readiness/permission/cancel cleanup remains; PCM worklet flush acknowledgment orders the last short chunk before commit.
- Correlated partial/final/failed transcript items remain ephemeral. Only authoritative completed events mark final. Terminal close waits for native drain/settlement, with a bounded30s uncertainty watchdog.
- All nine locales use the existing chat-studio namespace. No recordings/transcripts are persisted, logged or included in generic interaction telemetry.

## Evidence
Focused frontend/BFF/native protocol tests and local actual WebSocket+synthetic PCM browser proof are recorded in `local://realtime-transcription-notes.md`; main owns final shared architecture/catalog/stamp and release integration.
